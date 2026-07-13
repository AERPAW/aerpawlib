"""MAVSDK-backed multirotor implementation for the v1 API.

See ``aerpawlib.v1.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import TYPE_CHECKING

from mavsdk.action import ActionError
from mavsdk.mavlink_direct import MavlinkMessage
from mavsdk.offboard import OffboardError, PositionNedYaw, VelocityNedYaw
from pymavlink import mavutil

from aerpawlib.v1.constants import (
    COPTER_GUIDED_MODE,
    COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
    DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    GUIDED_MODE_NAME,
    HEADING_TOLERANCE_DEG,
    MAVLINK_MSG_COMMAND_LONG,
    MIN_ARM_TO_TAKEOFF_DELAY_S,
    OFFBOARD_STOP_SETTLE_DELAY_S,
    POLLING_DELAY_S,
    POST_TAKEOFF_STABILIZATION_S,
    TELEMETRY_SUBSCRIPTION_TIMEOUT_S,
    VELOCITY_UPDATE_DELAY_S,
)
from aerpawlib.v1.exceptions import (
    LandingError,
    NavigationError,
    NotArmableError,
    RTLError,
    TakeoffError,
    VelocityError,
)
from aerpawlib.v1.helpers import (
    heading_difference,
    normalize_heading,
    validate_tolerance,
    wait_for_condition,
)
from aerpawlib.v1.log import LogComponent, get_logger
from aerpawlib.v1.vehicle.core_vehicle import Vehicle

if TYPE_CHECKING:
    from aerpawlib.v1 import util

logger = get_logger(LogComponent.DRONE)


class Drone(Vehicle):
    """
    Drone implementation for multirotors.

    Provides core flight functionality including takeoff, landing,
    navigation, and velocity control.

    Attributes:
        _velocity_generation: Generation counter to detect stale velocity loops.
    """

    def __init__(self, connection_string: str, mavsdk_server_port: int = 50051):
        """
        Initialize the drone and check for startup constraints.

        Args:
            connection_string: MAVLink connection string.
            mavsdk_server_port: Port for the embedded mavsdk_server gRPC interface.
                Each Vehicle instance should use a unique port to avoid conflicts.
                Defaults to 50051.

        Raises:
            NotArmableError: If the vehicle is already armed (safety check).
        """
        super().__init__(connection_string, mavsdk_server_port=mavsdk_server_port)
        self._velocity_generation: int = 0
        self._offboard_active: bool = False
        # Wait for armed-state telemetry to arrive before checking
        start = time.time()
        while not self._ts_state.armed_telemetry_received.get():
            if time.time() - start > TELEMETRY_SUBSCRIPTION_TIMEOUT_S:
                logger.warning(
                    "Timeout waiting for armed-state telemetry; proceeding anyway",
                )
                break
            time.sleep(POLLING_DELAY_S)
        if self.armed and not ("127.0.0.1" in connection_string or "localhost" in connection_string):
            raise NotArmableError("Vehicle already armed at start!")

    async def set_heading(
        self,
        heading: float | None,
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """
        Command the drone to turn to a specific heading.

        Args:
            heading: Target heading in degrees (0-360).
                If None, clears any locked heading.
            blocking: Whether to wait for the drone to finish turning.
                Defaults to True.
            lock_in: If True, internal state will track this heading
                for future combined commands. Defaults to True.
        """
        if blocking:
            await self.await_ready_to_move()

        if heading is None:
            logger.debug("Clearing locked heading")
            self._current_heading = None
            return

        heading = normalize_heading(heading)
        if lock_in:
            self._current_heading = heading
        if not blocking:
            return

        logger.debug(f"Turning to {heading} (current: {self.heading})")
        try:
            # Compute current NED offset from home so the drone holds its
            # current position while rotating (rather than flying to home).
            home = self.home_coords
            if home is not None:
                offset = self.position - home
                north_m = offset.north
                east_m = offset.east
            else:
                north_m = 0.0
                east_m = 0.0

            await self._run_on_mavsdk_loop(
                self._system.offboard.set_position_ned(
                    PositionNedYaw(
                        north_m,
                        east_m,
                        -self.position.alt,
                        heading,
                    ),
                ),
            )
            try:
                await self._run_on_mavsdk_loop(self._system.offboard.start())
                self._offboard_active = True
            except OffboardError as e:
                logger.warning("Failed to start offboard mode: %s", e)

            self._ready_to_move = lambda s: heading_difference(heading, s.heading) <= HEADING_TOLERANCE_DEG
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
            )
        except (OffboardError, ActionError) as e:
            logger.warning(f"set_heading error: {e}")
        finally:
            # Ensure offboard mode is stopped
            try:
                await self._run_on_mavsdk_loop(self._system.offboard.stop())
                self._offboard_active = False
            except (OffboardError, ActionError):
                pass

    async def takeoff(
        self,
        target_alt: float,
        min_alt_tolerance: float = DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    ) -> None:
        """
        Perform a takeoff to the target altitude.

        Args:
            target_alt: Target altitude Above Ground Level (meters).
            min_alt_tolerance: Fraction of target altitude to reach before
                continuing. Defaults to DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE.

        Raises:
            TakeoffError: If the takeoff command fails or is rejected by the autopilot.
        """
        await self.await_ready_to_move()

        # Enforce minimum delay between arming and takeoff
        time_since_arm = time.time() - self._ts_state.last_arm_time.get()
        if time_since_arm < MIN_ARM_TO_TAKEOFF_DELAY_S:
            delay = MIN_ARM_TO_TAKEOFF_DELAY_S - time_since_arm
            logger.debug(
                f"Delaying takeoff by {delay:.2f}s to satisfy minimum arm-to-takeoff time",
            )
            await asyncio.sleep(delay)

        if self._mission_start_time is None:
            self._mission_start_time = time.time()

        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Taking off")
            logger.debug(f"Takeoff to {target_alt}m")
            await self._run_on_mavsdk_loop(
                self._system.action.set_takeoff_altitude(target_alt),
            )
            await self._run_on_mavsdk_loop(self._system.action.takeoff())

            self._ready_to_move = lambda s: s.position.alt >= target_alt * min_alt_tolerance
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
            )
            await asyncio.sleep(POST_TAKEOFF_STABILIZATION_S)
        except ActionError as e:
            logger.error(f"Takeoff failed: {e}")
            err_msg = f"Takeoff failed: {e}"
            if self.armed:
                err_msg += " (drone is already armed)"
            raise TakeoffError(err_msg, original_error=e) from e
        finally:
            update_progress(state="")

    async def _action_wait_disarm(self, coro, name, exc_cls):
        """
        Internal helper to execute an action and wait for the drone to disarm.

        Args:
            coro: The MAVSDK coroutine to run.
            name: Label for logging.
            exc_cls: Exception class to raise on failure.
        """
        await self.await_ready_to_move()
        self._abortable = False
        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Landing")
            logger.debug(f"Executing {name}, waiting for disarm...")
            await self._run_on_mavsdk_loop(coro)
            self._ready_to_move = lambda _: False
            await wait_for_condition(
                lambda: not self.armed,
                poll_interval=POLLING_DELAY_S,
            )
            logger.debug(f"{name} complete")
        except ActionError as e:
            logger.error(f"{name} failed: {e}")
            raise exc_cls(str(e), original_error=e) from e
        finally:
            update_progress(state="")

    async def land(self) -> None:
        """Land the drone and wait for it to be disarmed."""
        await self._action_wait_disarm(self._system.action.land(), "land", LandingError)

    async def return_to_launch(self) -> None:
        """Fly to home coordinates and land (RTL mode is not used)."""
        home = self.home_coords
        if home is None:
            logger.error("Return-to-launch requested but home coordinates are unset")
            raise RTLError("Home coordinates are not available for return-to-launch")
        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Returning home")
            await self.goto_coordinates(home)
            await self.land()
        except (NavigationError, LandingError) as e:
            logger.error(f"Return-to-launch failed: {e}")
            raise RTLError(str(e), original_error=e) from e
        finally:
            update_progress(state="")

    async def goto_coordinates(
        self,
        coordinates: util.Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
    ) -> None:
        """
        Make the vehicle go to provided coordinates.

        Args:
            coordinates: Target position
            tolerance: Distance in meters to consider destination reached
            target_heading: Optional heading to maintain during movement
            timeout: Maximum time to wait for completion in seconds (C3)

        Raises:
            ValueError: If tolerance is out of acceptable range
            NavigationError: If navigation command fails
        """
        validate_tolerance(tolerance, "tolerance")
        if target_heading is not None:
            await self.set_heading(target_heading, blocking=False)

        await self.await_ready_to_move()
        await self._stop()

        self._ready_to_move = lambda _: False
        heading = self._current_heading if self._current_heading is not None else self.position.bearing(coordinates)

        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Navigating")
            target_alt = coordinates.alt + self.home_amsl
            if self.home_amsl == 0.0 and self.home_coords is None:
                logger.warning(
                    "home_amsl is 0.0 and home position is not set; altitude may be incorrect. Use --skip-init only after home position is confirmed.",
                )
            logger.debug(
                f"Goto: {coordinates.lat}, {coordinates.lon}, alt={target_alt}, heading={heading}",
            )
            await self._run_on_mavsdk_loop(
                self._system.action.goto_location(
                    coordinates.lat,
                    coordinates.lon,
                    target_alt,
                    heading if not math.isnan(heading) else 0,
                ),
            )

            self._ready_to_move = lambda s: coordinates.distance(s.position) <= tolerance
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
                timeout=timeout,
                timeout_message=(f"Drone failed to reach destination {coordinates} within {timeout}s"),
            )
            logger.debug("Arrived at destination")
        except ActionError as e:
            logger.error(f"Goto failed: {e}")
            self._ready_to_move = lambda _: True
            raise NavigationError(str(e), original_error=e) from e
        except TimeoutError as e:
            logger.error(f"Goto timed out: {e}")
            raise NavigationError(str(e), original_error=e) from e
        finally:
            # Clear locked heading so it does not contaminate subsequent commands
            self._current_heading = None
            update_progress(state="")

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """
        [NOT SUPPORTED] This API function is not supported because velocity control is currently blocked by the filter. This may (and will) change in the future.

        Set the drone's velocity in NED frame.

        Args:
            velocity_vector: Target velocity.
            global_relative: If True, north/east are world-aligned.
                If False, they are relative to current heading. Defaults to True.
            duration: How long to maintain this velocity.
                If None, maintains it until stopped or changed.

        Raises:
            VelocityError: If offboard mode cannot be started.
        """
        await self.await_ready_to_move()
        self._velocity_generation += 1
        # Brief wait for previous velocity loop to observe change and exit
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)

        if not global_relative:
            velocity_vector = velocity_vector.rotate_by_angle(-self.heading)

        yaw = self._current_heading if self._current_heading is not None else self.heading
        logger.debug(f"Set velocity: {velocity_vector}, yaw={yaw}")
        if self._event_log:
            self._event_log.log_event(
                "command",
                type="set_velocity",
                north_m_s=velocity_vector.north,
                east_m_s=velocity_vector.east,
                down_m_s=velocity_vector.down,
                global_relative=global_relative,
                duration_s=duration,
                yaw_deg=yaw,
            )

        try:
            await self._run_on_mavsdk_loop(
                self._system.offboard.set_velocity_ned(
                    VelocityNedYaw(
                        velocity_vector.north,
                        velocity_vector.east,
                        velocity_vector.down,
                        yaw,
                    ),
                ),
            )
            try:
                await self._run_on_mavsdk_loop(self._system.offboard.start())
                self._offboard_active = True
            except OffboardError as e:
                logger.warning("Failed to start offboard mode: %s", e)

            self._ready_to_move = lambda _: True
            target_end = time.monotonic() + duration if duration is not None else None
            gen = self._velocity_generation

            async def _velocity_helper():
                """Maintain velocity command until cancelled or duration expires."""
                try:
                    while self._velocity_generation == gen:
                        if target_end and time.monotonic() > target_end:
                            # Zero velocity before stopping offboard to prevent
                            # the flight controller from holding the last
                            # commanded velocity vector
                            try:
                                await self._run_on_mavsdk_loop(
                                    self._system.offboard.set_velocity_ned(
                                        VelocityNedYaw(0, 0, 0, yaw),
                                    ),
                                )
                                await asyncio.sleep(OFFBOARD_STOP_SETTLE_DELAY_S)
                            except (OffboardError, ActionError):
                                pass
                            try:
                                await self._run_on_mavsdk_loop(
                                    self._system.offboard.stop(),
                                )
                                self._offboard_active = False
                            except (OffboardError, ActionError):
                                logger.warning("Failed to stop offboard mode cleanly")
                            return
                        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)
                except Exception as e:
                    logger.error(f"Velocity helper error: {e}")
                    try:
                        await self._run_on_mavsdk_loop(
                            self._system.offboard.set_velocity_ned(
                                VelocityNedYaw(0, 0, 0, 0),
                            ),
                        )
                        await self._run_on_mavsdk_loop(self._system.offboard.stop())
                        self._offboard_active = False
                    except Exception as e:
                        logger.debug("Velocity helper cleanup failed: %s", e)

            task = asyncio.create_task(_velocity_helper())
            self._command_tasks.append(task)
        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e) from e

    async def _stop(self) -> None:
        """Stop drone-specific offboard control during shutdown."""
        await super()._stop()
        self._velocity_generation += 1
        # Only exit offboard mode if we were actually running it.
        # Calling offboard.stop() when not in offboard mode causes ArduPilot
        # to switch to LOITER, which creates unnecessary GUIDED→LOITER→GUIDED
        # churn on every waypoint transition.
        if self._offboard_active:
            try:
                await self._run_on_mavsdk_loop(
                    self._system.offboard.set_velocity_ned(
                        VelocityNedYaw(0, 0, 0, self.heading),
                    ),
                )
                await self._run_on_mavsdk_loop(self._system.offboard.stop())
            except Exception as e:
                logger.debug("Stop offboard cleanup (may not be in offboard): %s", e)
            finally:
                self._offboard_active = False

    async def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode.

        ArduPilot Drone/Copter requires GUIDED mode to accept takeoff/navigation commands.
        We send MAV_CMD_DO_SET_MODE directly using mavlink_direct,
        then poll until the flight controller confirms the mode change.
        """
        if self._ts_state.mode.get() == GUIDED_MODE_NAME:
            logger.debug(
                f"Drone: already in GUIDED ({GUIDED_MODE_NAME}) mode, skipping mode switch",
            )
            return
        logger.info(
            f"Drone: switching to GUIDED ({GUIDED_MODE_NAME}) mode (current mode={self._ts_state.mode.get()!r})",
        )
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
        try:
            await self._run_on_mavsdk_loop(
                self._system.mavlink_direct.send_message(msg),
            )
        except Exception as e:
            logger.warning(
                f"Drone: failed to send GUIDED ({GUIDED_MODE_NAME}) mode command: {e}",
            )
            return

        start = time.time()
        while self._ts_state.mode.get() != GUIDED_MODE_NAME:
            if time.time() - start > COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S:
                logger.warning(
                    f"Drone: mode switch timeout (current mode={self._ts_state.mode.get()!r}); commands may fail if vehicle is not in GUIDED ({GUIDED_MODE_NAME}) mode",
                )
                return
            await asyncio.sleep(POLLING_DELAY_S)
        logger.info(f"Drone: GUIDED ({GUIDED_MODE_NAME}) mode confirmed")

