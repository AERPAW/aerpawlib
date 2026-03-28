"""
Drone vehicle for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Optional

from mavsdk.action import ActionError
from mavsdk.offboard import OffboardError, PositionNedYaw, VelocityNedYaw

from ..constants import (
    ARMING_SEQUENCE_DELAY_S,
    CONNECTION_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
    DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    GPS_3D_FIX_TYPE,
    GOTO_LOG_INTERVAL_S,
    GOTO_NB_LOG_INTERVAL_S,
    HEADING_TOLERANCE_DEG,
    HOME_POSITION_TIMEOUT_S,
    MIN_ARM_TO_TAKEOFF_DELAY_S,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
    POST_ARM_STABILIZE_DELAY_S,
    POST_TAKEOFF_STABILIZATION_S,
    TAKEOFF_LOG_INTERVAL_S,
    VELOCITY_UPDATE_DELAY_S,
)
from ..exceptions import (
    LandingError,
    NavigationError,
    RTLError,
    TakeoffError,
    VelocityError,
)
from ..log import LogComponent, get_logger
from ..types import Coordinate, VectorNED
from .base import Vehicle, VehicleTask, _validate_tolerance, _wait_for_condition
from .heading import _heading_diff, _normalize_heading

logger = get_logger(LogComponent.DRONE)


class Drone(Vehicle):
    """Drone implementation for multirotors."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise the Drone, forwarding all arguments to Vehicle."""
        super().__init__(*args, **kwargs)
        self._current_heading: Optional[float] = None
        self._velocity_loop_active = False
        self._offboard_in_use: bool = False

    async def _preflight_wait(self, should_arm: bool = True) -> None:
        """Wait for pre-arm conditions. Call before run."""
        self._will_arm = should_arm
        from ..constants import (
            ARMABLE_TIMEOUT_S,
            ARMABLE_STATUS_LOG_INTERVAL_S,
            POLLING_DELAY_S,
        )

        start = time.monotonic()
        last_log = 0.0
        while not self._state.armable:
            if time.monotonic() - start > ARMABLE_TIMEOUT_S:
                logger.warning(
                    f"Timeout waiting for armable ({ARMABLE_TIMEOUT_S}s). "
                    f"Status: {self._get_health_summary()}"
                )
                break
            if time.monotonic() - last_log > ARMABLE_STATUS_LOG_INTERVAL_S:
                logger.debug(f"Waiting for armable... {self._get_health_summary()}")
                last_log = time.monotonic()
            await asyncio.sleep(POLLING_DELAY_S)

    async def _arm_vehicle(self) -> None:
        """Arm and prepare for mission (SITL/standalone: auto-arm)."""
        from ..constants import ARMING_SEQUENCE_DELAY_S, POSITION_READY_TIMEOUT_S

        if not self._will_arm:
            logger.debug("Drone: _arm_vehicle skipped (_will_arm=False)")
            return
        await _wait_for_condition(
            lambda: self._state.armable,
            timeout=CONNECTION_TIMEOUT_S,
            timeout_message=f"Vehicle not armable: {self._get_health_summary()}",
        )
        await _wait_for_condition(
            lambda: self.gps.fix_type >= GPS_3D_FIX_TYPE,
            timeout=POSITION_READY_TIMEOUT_S,
            timeout_message="No GPS 3D fix",
        )
        while not self.ekf_ready:
            await asyncio.sleep(POST_ARM_STABILIZE_DELAY_S)
        await self.set_armed(True)
        await asyncio.sleep(ARMING_SEQUENCE_DELAY_S)
        await _wait_for_condition(
            lambda: self._state.home_coords is not None,
            timeout=HOME_POSITION_TIMEOUT_S,
            timeout_message="Home position not available",
        )

    async def set_heading(
        self,
        heading: Optional[float],
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """Command the drone to face a given heading.

        Args:
            heading: Target heading in degrees (0–360). Pass None to clear
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
        self._offboard_in_use = True
        home = self.home_coords
        if home:
            offset = self.position - home  # VectorNED
            north_m, east_m = offset.north, offset.east
        else:
            north_m, east_m = 0.0, 0.0
        try:
            await self._system.offboard.set_position_ned(
                PositionNedYaw(north_m, east_m, -self.position.alt, heading)
            )
            try:
                await self._system.offboard.start()
            except OffboardError:
                pass
            self._ready_to_move = (
                lambda s: _heading_diff(heading, s.heading) <= HEADING_TOLERANCE_DEG
            )
            await _wait_for_condition(
                lambda: self.done_moving(), timeout=DEFAULT_GOTO_TIMEOUT_S
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
                "command", type="takeoff", arguments={"altitude": altitude}
            )
        await self.await_ready_to_move()
        time_since_arm = time.monotonic() - self._state.last_arm_time
        if time_since_arm < MIN_ARM_TO_TAKEOFF_DELAY_S:
            delay = MIN_ARM_TO_TAKEOFF_DELAY_S - time_since_arm
            logger.debug(f"Drone: takeoff awaiting min arm delay ({delay:.1f}s)")
            await asyncio.sleep(delay)  # Justified: min arm-to-takeoff delay
        if self._mission_start_time is None:
            self._mission_start_time = time.time()
        try:
            logger.debug(
                f"Drone: takeoff sending set_takeoff_altitude({altitude}m) and takeoff()"
            )
            await self._system.action.set_takeoff_altitude(altitude)
            await self._system.action.takeoff()
            self._ready_to_move = (
                lambda s: s.position.alt >= altitude * min_alt_tolerance
            )
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
                POST_TAKEOFF_STABILIZATION_S
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
            raise TakeoffError(str(e), original_error=e)

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
        try:
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
            raise LandingError(str(e), original_error=e)
        finally:
            self._expecting_disarm = False

    async def return_to_launch(self) -> None:
        """Command Return-to-Launch (RTL) and wait for disarm.

        Raises:
            RTLError: If the RTL command fails or times out.
        """
        await self.await_ready_to_move()
        if self._event_log:
            self._event_log.log_event("command", type="return_to_launch")
        try:
            logger.debug("Drone: return_to_launch sending RTL command")
            await self._system.action.return_to_launch()
            self._expecting_disarm = True
            await _wait_for_condition(
                lambda: not self.armed,
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message="Drone: return_to_launch timed out waiting for disarm",
            )
        except (ActionError, TimeoutError) as e:
            logger.error(f"Drone: return_to_launch failed: {e}")
            raise RTLError(str(e), original_error=e)
        finally:
            self._expecting_disarm = False

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
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
        if self._offboard_in_use:
            await self._stop_offboard()
        heading = (
            self._current_heading
            if self._current_heading is not None
            else self.position.bearing(coordinates)
        )
        if math.isnan(heading):
            heading = 0.0
        target_alt = coordinates.alt + self.home_amsl
        if self.home_amsl == 0.0 and self._state.home_coords is None:
            logger.warning(
                "Drone: home AMSL altitude is 0.0 and home position not yet received. "
                "goto_coordinates altitude may be incorrect (treating coordinates.alt as AMSL). "
                "Use --skip-init only when the vehicle is already armed and home is set."
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
                coordinates.lat, coordinates.lon, target_alt, heading
            )
        except ActionError as e:
            logger.error(f"Drone: goto_location failed: {e}")
            self._ready_to_move = lambda _: True  # reset so next command isn't blocked
            raise NavigationError(str(e), original_error=e)
        finally:
            self._current_heading = None
        self._ready_to_move = lambda s: coordinates.distance(s.position) <= tolerance

        if blocking:
            start = time.monotonic()
            last_log = 0.0
            while not self.done_moving():
                elapsed = time.monotonic() - start
                if elapsed > timeout:
                    raise TimeoutError(f"Goto timed out within {timeout}s")
                now = time.monotonic()
                if now - last_log >= GOTO_LOG_INTERVAL_S:
                    dist = coordinates.distance(self.position)
                    logger.debug(
                        "Drone: goto_coordinates progress dist=%.1fm tol=%.1fm elapsed=%.0fs",
                        dist,
                        tolerance,
                        elapsed,
                    )
                    last_log = now
                await asyncio.sleep(POLLING_DELAY_S)
            logger.debug("Drone: goto_coordinates complete (blocking)")
            if self._event_log:
                self._event_log.log_event(
                    "location",
                    lat=self.position.lat,
                    lon=self.position.lon,
                    alt=self.position.alt,
                )
            return None

        handle = VehicleTask()
        logger.debug("Drone: goto_coordinates returning non-blocking VehicleTask")

        async def _on_cancel() -> None:
            if not self._closed and self._system is not None:
                await self.return_to_launch()
            else:
                logger.warning("Drone: _on_cancel skipped (vehicle closed)")

        handle.set_on_cancel(_on_cancel)

        initial_dist = coordinates.distance(self.position)

        async def _wait_arrival() -> None:
            try:
                await _wait_for_condition(
                    lambda: self.done_moving() or handle.is_cancelled(),
                    timeout=timeout,
                )
                if handle.is_cancelled():
                    handle.set_complete()
                    return
                if self._event_log:
                    self._event_log.log_event(
                        "location",
                        lat=self.position.lat,
                        lon=self.position.lon,
                        alt=self.position.alt,
                    )
                handle.set_progress(1.0)
                handle.set_complete()
            except TimeoutError as e:
                handle.set_error(NavigationError(str(e), original_error=e))
            except Exception as e:
                handle.set_error(e)

        async def _progress_updater() -> None:
            last_log = 0.0
            while not handle.is_done():
                if handle.is_cancelled():
                    return
                d = coordinates.distance(self.position)
                if initial_dist > 0:
                    p = 1.0 - (d / initial_dist)
                    handle.set_progress(max(0.0, min(1.0, p)))
                now = time.monotonic()
                if now - last_log >= GOTO_NB_LOG_INTERVAL_S:
                    logger.debug(
                        "Drone: goto_coordinates (non-blocking) dist=%.1fm progress=%.0f%%",
                        d,
                        handle.progress * 100,
                    )
                    last_log = now
                await asyncio.sleep(0.2)  # Justified: progress polling interval

        t1 = asyncio.create_task(_wait_arrival())
        t2 = asyncio.create_task(_progress_updater())
        self._command_tasks.extend([t1, t2])
        return handle

    async def goto_north(
        self,
        meters: float,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` north from current position.

        Args:
            meters: Distance to travel north in metres.
            tolerance: Arrival radius in metres (default 2 m).
            target_heading: Optional heading to face before navigating.
            timeout: Maximum seconds to wait when blocking (default 300 s).
            blocking: If True (default), await arrival before returning.

        Returns:
            None when blocking=True; a VehicleTask handle when blocking=False.
        """
        target = self.position + VectorNED(meters, 0, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_east(
        self,
        meters: float,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` east from current position."""
        target = self.position + VectorNED(0, meters, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_south(
        self,
        meters: float,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` south from current position."""
        target = self.position + VectorNED(-meters, 0, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_west(
        self,
        meters: float,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` west from current position."""
        target = self.position + VectorNED(0, -meters, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_ned(
        self,
        north: float,
        east: float,
        down: float = 0,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go by NED offset from current position.

        Args:
            north: North component in metres (positive = north).
            east: East component in metres (positive = east).
            down: Down component in metres (positive = down, optional).
            tolerance: Arrival radius in metres.
            target_heading: Optional heading to face before navigating.
            timeout: Maximum seconds to wait when blocking.
            blocking: If True (default), await arrival before returning.

        Returns:
            None when blocking=True; a VehicleTask handle when blocking=False.
        """
        target = self.position + VectorNED(north, east, down)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_bearing(
        self,
        bearing_deg: float,
        distance_m: float,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Fly along ``bearing_deg`` for ``distance_m`` metres from current position.

        Bearing: 0=north, 90=east, 180=south, 270=west.

        Args:
            bearing_deg: Bearing in degrees (0–360).
            distance_m: Distance to travel in metres.
            tolerance: Arrival radius in metres.
            target_heading: Optional heading to face before navigating.
            timeout: Maximum seconds to wait when blocking.
            blocking: If True (default), await arrival before returning.

        Returns:
            None when blocking=True; a VehicleTask handle when blocking=False.
        """
        v = VectorNED(distance_m, 0, 0).rotate_by_angle(-bearing_deg)
        target = self.position + v
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def set_velocity(
        self,
        velocity: VectorNED,
        global_relative: bool = True,
        duration: Optional[float] = None,
    ) -> None:
        """Set the drone's velocity in the NED frame.

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
            f"Drone: set_velocity NED=({velocity.north:.2f}, {velocity.east:.2f}, "
            f"{velocity.down:.2f}) m/s, duration={duration}s"
        )
        await self.await_ready_to_move()
        self._velocity_loop_active = False
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)  # Let previous loop exit
        if not global_relative:
            velocity = velocity.rotate_by_angle(-self.heading)
        yaw = (
            self._current_heading if self._current_heading is not None else self.heading
        )
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
                VelocityNedYaw(velocity.north, velocity.east, velocity.down, yaw)
            )
            try:
                await self._system.offboard.start()
            except OffboardError:
                pass
            self._offboard_in_use = True
            self._ready_to_move = lambda _: True
            target_end = time.monotonic() + duration if duration else None

            async def _velocity_loop() -> None:
                """Maintain velocity command until duration or cancellation."""
                try:
                    while self._velocity_loop_active:
                        if target_end and time.monotonic() > target_end:
                            logger.debug(
                                "Drone: set_velocity duration reached, stopping offboard"
                            )
                            self._velocity_loop_active = False
                            await self._system.offboard.set_velocity_ned(
                                VelocityNedYaw(0, 0, 0, yaw)
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
                    self._velocity_loop_active = False
                    try:
                        await self._system.offboard.set_velocity_ned(
                            VelocityNedYaw(0, 0, 0, 0)
                        )
                        await self._system.offboard.stop()
                    except Exception:
                        pass

            self._velocity_loop_active = True
            vel_task = asyncio.create_task(_velocity_loop())
            self._command_tasks.append(vel_task)
            logger.debug("Drone: set_velocity offboard started, velocity loop active")
        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e)

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
        self._velocity_loop_active = False
        self._offboard_in_use = False
        if self._closed or self._system is None:
            logger.debug("_stop_offboard: skipped (vehicle closed)")
            return
        try:
            await self._system.offboard.set_velocity_ned(
                VelocityNedYaw(0, 0, 0, self.heading)
            )
            await self._system.offboard.stop()
        except Exception:
            logger.debug("Stop offboard (may not be in offboard)")

    async def _stop(self) -> None:
        """Stop drone-specific background control before final shutdown."""
        await super()._stop()
        await self._stop_offboard()
