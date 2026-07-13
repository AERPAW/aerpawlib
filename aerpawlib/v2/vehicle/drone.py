"""MAVSDK-backed multirotor implementation for the v2 API.

See ``aerpawlib.v2.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time

from mavsdk.action import ActionError
from mavsdk.mavlink_direct import MavlinkMessage
from mavsdk.offboard import OffboardError, PositionNedYaw, VelocityNedYaw
from pymavlink import mavutil

from aerpawlib.v2.constants import (
    COPTER_GUIDED_MODE,
    COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
    DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    HEADING_TOLERANCE_DEG,
    MAVLINK_MSG_COMMAND_LONG,
    MIN_ARM_TO_TAKEOFF_DELAY_S,
    POLLING_DELAY_S,
    POST_TAKEOFF_STABILIZATION_S,
    TAKEOFF_LOG_INTERVAL_S,
    VELOCITY_UPDATE_DELAY_S,
)
from aerpawlib.v2.exceptions import (
    LandingError,
    NavigationError,
    RTLError,
    TakeoffError,
    VelocityError,
)
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.types import Coordinate, VectorNED

from .base import Vehicle, _wait_for_condition
from .connection_helpers import _validate_tolerance
from .heading import _heading_diff, _normalize_heading
from .navigation import start_nonblocking_goto, wait_for_blocking_goto
from .task import VehicleTask

logger = get_logger(LogComponent.DRONE)


class Drone(Vehicle):
    """Drone implementation for multirotors."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise the Drone, forwarding all arguments to Vehicle."""
        super().__init__(*args, **kwargs)
        self._current_heading: float | None = None

    def _standalone_arm_wait_ekf(self) -> bool:
        return True

    async def set_heading(
        self,
        heading: float | None,
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """Command the drone to face a given heading.

        Args:
            heading: Target heading in degrees (0-360). Pass None to clear
                the currently locked heading.
            blocking: If True (default), wait until the heading is reached
                before returning.
            lock_in: If True (default), store the heading so subsequent
                goto_coordinates commands maintain it.
        """
        if blocking:
            await self.await_ready_to_move()
        if heading is None:
            logger.debug("Drone: set_heading(None) clearing heading lock")
            self._current_heading = None
            return
        heading = _normalize_heading(heading)
        logger.debug(f"Drone: set_heading({heading:.1f} deg) blocking={blocking}")
        if lock_in:
            self._current_heading = heading
        if not blocking:
            return
        self._offboard.mark_active()
        home = self.home_coords
        if home:
            offset = self.position - home  # VectorNED
            north_m, east_m = offset.north, offset.east
        else:
            north_m, east_m = 0.0, 0.0
        try:
            await self._system.offboard.set_position_ned(
                PositionNedYaw(north_m, east_m, -self.position.alt, heading),
            )
            with contextlib.suppress(OffboardError):
                await self._system.offboard.start()
            self._ready_to_move = lambda s: _heading_diff(heading, s.heading) <= HEADING_TOLERANCE_DEG
            await _wait_for_condition(
                lambda: self.done_moving(),
                timeout=DEFAULT_GOTO_TIMEOUT_S,
            )
        except (OffboardError, ActionError) as e:
            logger.warning(f"set_heading error: {e}")
        else:
            logger.debug(f"Drone: set_heading complete (heading={heading:.1f} deg)")
        finally:
            await self._stop_offboard()

    async def takeoff(
        self,
        altitude: float,
        min_alt_tolerance: float = DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    ) -> None:
        """Command the drone to take off to the given altitude.

        Args:
            altitude: Target relative altitude in metres above the home point.
            min_alt_tolerance: Fraction of the target altitude that must be
                reached before takeoff is considered complete (default 0.95).

        Raises:
            TakeoffError: If the MAVSDK takeoff command fails.
        """
        if self._event_log:
            self._event_log.log_event(
                "command",
                type="takeoff",
                arguments={"altitude": altitude},
            )
        await self.await_ready_to_move()
        time_since_arm = time.monotonic() - self._state.last_arm_time
        if time_since_arm < MIN_ARM_TO_TAKEOFF_DELAY_S:
            delay = MIN_ARM_TO_TAKEOFF_DELAY_S - time_since_arm
            logger.debug(f"Drone: takeoff awaiting min arm delay ({delay:.1f}s)")
            await asyncio.sleep(delay)  # Justified: min arm-to-takeoff delay
        if self._mission_start_time is None:
            self._mission_start_time = time.time()
        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Taking off")
            logger.debug(
                "Drone: takeoff sending set_takeoff_altitude({altitude}m) and takeoff()",
            )
            await self._system.action.set_takeoff_altitude(altitude)
            await self._system.action.takeoff()
            self._ready_to_move = lambda s: s.position.alt >= altitude * min_alt_tolerance
            last_log = 0.0
            while not self.done_moving():
                now = time.monotonic()
                if now - last_log >= TAKEOFF_LOG_INTERVAL_S:
                    logger.debug(
                        "Drone: takeoff climbing alt=%.1fm target=%.1fm",
                        self.position.alt,
                        altitude,
                    )
                    last_log = now
                await asyncio.sleep(POLLING_DELAY_S)
            await asyncio.sleep(
                POST_TAKEOFF_STABILIZATION_S,
            )  # Justified: stabilization
            if self._event_log:
                self._event_log.log_event(
                    "takeoff",
                    altitude=altitude,
                    lat=self.position.lat,
                    lon=self.position.lon,
                )
        except ActionError as e:
            logger.error(f"Drone: takeoff failed: {e}")
            err_msg = f"Takeoff failed: {e}"
            if self.armed:
                err_msg += " (drone is already armed)"
            raise TakeoffError(err_msg, original_error=e) from e
        finally:
            update_progress(state="")

    async def land(self) -> None:
        """Command the drone to land and wait for disarm.

        Raises:
            LandingError: If the land command fails or times out.
        """
        if self._event_log:
            self._event_log.log_event("command", type="land")
        await self.await_ready_to_move()
        if self._event_log:
            self._event_log.log_event("land_start")
        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Landing")
            logger.debug("Drone: land sending land() command")
            await self._system.action.land()
            self._expecting_disarm = True
            await _wait_for_condition(
                lambda: not self.armed,
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message="Drone: land timed out waiting for disarm",
            )
            if self._event_log:
                self._event_log.log_event("land_complete")
        except (ActionError, TimeoutError) as e:
            logger.error(f"Drone: land failed: {e}")
            raise LandingError(str(e), original_error=e) from e
        finally:
            self._expecting_disarm = False
            update_progress(state="")

    async def return_to_launch(self) -> None:
        """Fly to home coordinates and land (RTL mode is not used).

        Raises:
            RTLError: If returning home or landing fails.
        """
        home = self.home_coords
        if home is None:
            logger.error("Drone: return_to_launch requires home coordinates")
            raise RTLError("Home coordinates are not available for return_to_launch")
        if self._event_log:
            self._event_log.log_event("command", type="return_to_launch")
        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Returning home")
            logger.debug("Drone: return_to_launch navigating home then landing")
            await self.goto_coordinates(home)
            await self.land()
        except (NavigationError, LandingError, TimeoutError) as e:
            logger.error(f"Drone: return_to_launch failed: {e}")
            raise RTLError(str(e), original_error=e) from e
        finally:
            update_progress(state="")

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Fly to the given coordinates.

        Args:
            coordinates: Target position (lat, lon, relative alt in metres).
            tolerance: Arrival radius in metres (default 2 m).
            target_heading: Optional heading to face before navigating.
            timeout: Maximum seconds to wait when blocking (default 300 s).
            blocking: If True (default), await arrival before returning.
                If False, return a VehicleTask handle immediately.

        Returns:
            None when blocking=True; a VehicleTask handle when blocking=False.

        Raises:
            NavigationError: If the goto_location MAVSDK call fails.
            TimeoutError: If blocking=True and the drone does not arrive within
                timeout.
        """
        if self._event_log:
            self._event_log.log_event(
                "command",
                type="goto_coordinates",
                arguments={
                    "target_lat": coordinates.lat,
                    "target_lon": coordinates.lon,
                    "target_alt": coordinates.alt,
                },
            )
        _validate_tolerance(tolerance, "tolerance")
        if target_heading is not None:
            await self.set_heading(target_heading, blocking=False)
        await self.await_ready_to_move()
        if self._offboard.active:
            await self._stop_offboard()
        heading = self._current_heading if self._current_heading is not None else self.position.bearing(coordinates)
        if math.isnan(heading):
            heading = 0.0
        target_alt = coordinates.alt + self.home_amsl
        if self.home_amsl == 0.0 and self._state.home_coords is None:
            logger.warning(
                "Drone: home AMSL altitude is 0.0 and home position not yet received. goto_coordinates altitude may be incorrect (treating coordinates.alt as AMSL). Use --skip-init only when the vehicle is already armed and home is set.",
            )
        try:
            logger.debug(
                "Drone: goto_coordinates sending goto_location(%.6f, %.6f, alt=%.1f, hdg=%.1f)",
                coordinates.lat,
                coordinates.lon,
                target_alt,
                heading,
            )
            self._ready_to_move = lambda _: False
            await self._system.action.goto_location(
                coordinates.lat,
                coordinates.lon,
                target_alt,
                heading,
            )
        except ActionError as e:
            logger.error(f"Drone: goto_location failed: {e}")
            self._ready_to_move = lambda _: True  # reset so next command isn't blocked
            raise NavigationError(str(e), original_error=e) from e
        finally:
            self._current_heading = None
        self._ready_to_move = lambda s: coordinates.distance(s.position) <= tolerance

        if blocking:
            from aerpawlib.cli.progress_bar import update_progress

            try:
                update_progress(state="Navigating")
                await wait_for_blocking_goto(
                    self,
                    coordinates,
                    distance_fn=lambda: coordinates.distance(self.position),
                    tolerance=tolerance,
                    timeout=timeout,
                    log_prefix="Drone",
                )
                logger.debug("Drone: goto_coordinates complete (blocking)")
                if self._event_log:
                    self._event_log.log_event(
                        "location",
                        lat=self.position.lat,
                        lon=self.position.lon,
                        alt=self.position.alt,
                    )
                return None
            finally:
                update_progress(state="")

        def _log_location() -> None:
            if self._event_log:
                self._event_log.log_event(
                    "location",
                    lat=self.position.lat,
                    lon=self.position.lon,
                    alt=self.position.alt,
                )

        async def _on_cancel() -> None:
            if not self.closed and self._system is not None:
                await self.return_to_launch()
            else:
                logger.warning("Drone: _on_cancel skipped (vehicle closed)")

        return start_nonblocking_goto(
            self,
            coordinates,
            distance_fn=lambda: coordinates.distance(self.position),
            tolerance=tolerance,
            timeout=timeout,
            on_cancel=_on_cancel,
            log_prefix="Drone",
            on_complete=_log_location,
        )

    async def set_velocity(
        self,
        velocity: VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """[NOT SUPPORTED] This API function is not supported because velocity control is currently blocked by the filter. This may (and will) change in the future.

        Set the drone's velocity in the NED frame.

        Enters offboard mode and sends the velocity setpoint. The velocity loop
        runs until the next movement command or until duration expires.

        Args:
            velocity: Desired velocity as a NED vector (m/s).
            global_relative: If True (default), the vector is in the global NED
                frame. If False, the vector is rotated by the drone's current
                heading before being sent.
            duration: If given, hold the velocity for this many seconds then
                stop. If None, the velocity runs until the next command.

        Raises:
            VelocityError: If offboard mode cannot be started.
        """
        logger.info(
            f"Drone: set_velocity NED=({velocity.north:.2f}, {velocity.east:.2f}, {velocity.down:.2f}) m/s, duration={duration}s",
        )
        await self.await_ready_to_move()
        self._offboard.stop_velocity_loop()
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)  # Let previous loop exit
        if not global_relative:
            velocity = velocity.rotate_by_angle(-self.heading)
        yaw = self._current_heading if self._current_heading is not None else self.heading
        if self._event_log:
            self._event_log.log_event(
                "command",
                type="set_velocity",
                north_m_s=velocity.north,
                east_m_s=velocity.east,
                down_m_s=velocity.down,
                global_relative=global_relative,
                duration_s=duration,
                yaw_deg=yaw,
            )
        try:
            await self._system.offboard.set_velocity_ned(
                VelocityNedYaw(velocity.north, velocity.east, velocity.down, yaw),
            )
            with contextlib.suppress(OffboardError):
                await self._system.offboard.start()
            self._offboard.mark_active()
            self._ready_to_move = lambda _: True
            target_end = time.monotonic() + duration if duration else None

            async def _velocity_loop() -> None:
                """Maintain velocity command until duration or cancellation."""
                try:
                    while self._offboard.velocity_loop_active:
                        if target_end and time.monotonic() > target_end:
                            logger.debug(
                                "Drone: set_velocity duration reached, stopping offboard",
                            )
                            self._offboard.stop_velocity_loop()
                            await self._system.offboard.set_velocity_ned(
                                VelocityNedYaw(0, 0, 0, yaw),
                            )
                            await asyncio.sleep(0.05)
                            await self._system.offboard.stop()
                            return
                        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)
                    logger.debug("Drone: set_velocity loop exited")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Velocity loop error: {e}")
                    self._offboard.stop_velocity_loop()
                    try:
                        await self._system.offboard.set_velocity_ned(
                            VelocityNedYaw(0, 0, 0, 0),
                        )
                        await self._system.offboard.stop()
                    except Exception:
                        pass

            self._offboard.velocity_loop_active = True
            vel_task = asyncio.create_task(_velocity_loop())
            self._command_tasks.append(vel_task)
            logger.debug("Drone: set_velocity offboard started, velocity loop active")
        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e) from e

    async def stop_velocity(self) -> None:
        """Stop any active velocity command and exit offboard mode.

        Call this to halt motion after :meth:`set_velocity` when no ``duration``
        was specified, or to abort a velocity command early.
        """
        if self._event_log:
            self._event_log.log_event("command", type="stop_velocity")
        logger.info("Drone: stop_velocity")
        await self._stop_offboard()

    async def _stop_offboard(self) -> None:
        """Stop offboard mode and zero velocity setpoint."""
        await self._offboard.stop(
            self._system,
            self.heading,
            closed=self.closed,
        )

    async def _stop(self) -> None:
        """Stop drone-specific background control before final shutdown."""
        await super()._stop()
        await self._stop_offboard()

    async def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode.

        ArduPilot Drone/Copter requires GUIDED mode to accept takeoff/navigation commands.
        We send MAV_CMD_DO_SET_MODE directly using mavlink_direct,
        then poll until the flight controller confirms the mode change.
        """
        if self.mode == "OFFBOARD":
            logger.debug(
                "Drone: already in GUIDED (OFFBOARD) mode, skipping mode switch",
            )
            return
        logger.info(
            f"Drone: switching to GUIDED (OFFBOARD) mode (current mode={self.mode!r})",
        )
        try:
            fields = {
                "target_system": 1,
                "target_component": 1,
                "command": mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                "confirmation": 0,
                "param1": float(mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED),
                "param2": float(COPTER_GUIDED_MODE),
                "param3": 0.0,
                "param4": 0.0,
                "param5": 0.0,
                "param6": 0.0,
                "param7": 0.0,
            }
            msg = MavlinkMessage(
                system_id=1,
                component_id=1,
                target_system_id=1,
                target_component_id=1,
                message_name=MAVLINK_MSG_COMMAND_LONG,
                fields_json=json.dumps(fields),
            )
        except Exception as e:
            logger.warning(f"Drone: failed to prepare GUIDED (OFFBOARD) mode fields: {e}")
            return

        async def _send_and_check() -> bool:
            try:
                await self._system.mavlink_direct.send_message(msg)
            except Exception as e:
                logger.warning(f"Drone: failed to send GUIDED (OFFBOARD) mode command: {e}")
            await asyncio.sleep(0.5)
            return self.mode == "OFFBOARD"

        try:
            await _wait_for_condition(
                _send_and_check,
                timeout=COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S,
                timeout_message=(f"Drone did not enter GUIDED (OFFBOARD) mode within {COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S}s"),
            )
            logger.info("Drone: GUIDED (OFFBOARD) mode confirmed")
        except TimeoutError:
            logger.warning(
                f"Drone: mode switch timeout (current mode={self.mode!r}); commands may fail if vehicle is not in GUIDED (OFFBOARD) mode",
            )

