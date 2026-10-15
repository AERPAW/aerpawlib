"""MAVSDK-backed ground vehicle implementation for the v1 API.

See ``aerpawlib.v1.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from aerpawlib.v1.log import LogComponent, get_logger

try:
    from mavsdk.action import ActionError
except ImportError:
    ActionError = Exception

from typing import TYPE_CHECKING

from aerpawlib.v1.constants import (
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_ROVER_POSITION_TOLERANCE_M,
    GUIDED_MODE_NAME,
    MAVLINK_COMMAND_TIMEOUT_S,
    POLLING_DELAY_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    VELOCITY_UPDATE_DELAY_S,
)
from aerpawlib.v1.exceptions import (
    NavigationError,
    VelocityError,
)
from aerpawlib.v1.helpers import (
    validate_tolerance,
)
from aerpawlib.v1.vehicle.core_vehicle import Vehicle

if TYPE_CHECKING:
    from aerpawlib.v1 import util

logger = get_logger(LogComponent.ROVER)


class Rover(Vehicle):
    """
    Rover implementation for ground vehicles.

    Focuses on 2D ground navigation using MAVSDK's action.goto_location.

    Note:
        `target_heading` is currently ignored during movement as the
        MAVLink mission item for navigation usually handles steering.
    """

    def __init__(self, connection_string: str, mavsdk_server_port: int = 50051):
        """
        Initialize the rover.

        Args:
            connection_string: MAVLink connection string.
            mavsdk_server_port: Port for the embedded mavsdk_server gRPC interface.
                Each Vehicle instance should use a unique port to avoid conflicts.
                Defaults to 50051.
        """
        super().__init__(connection_string, mavsdk_server_port=mavsdk_server_port)
        self._velocity_generation: int = 0
        self._velocity_active: bool = False

    async def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode before arming.

        ArduPilot Rover requires GUIDED mode to accept arm commands via
        MAVLink. We send MAV_CMD_DO_SET_MODE directly using mavlink_direct,
        then poll until the flight controller confirms the mode change.
        """
        if self._ts_state.mode.get() == GUIDED_MODE_NAME:
            logger.debug(
                f"Rover: already in GUIDED ({GUIDED_MODE_NAME}) mode, skipping mode switch",
            )
            return
        logger.info(
            f"Rover: switching to GUIDED ({GUIDED_MODE_NAME}) mode (current mode={self._ts_state.mode.get()!r})",
        )
        from aerpawlib._internal.mavlink_ids import make_set_mode_message, resolve_mav_sysid

        sysid = resolve_mav_sysid(self._system)
        msg = make_set_mode_message(sysid, ROVER_GUIDED_MODE)
        try:
            # gRPC calls must run on the MAVSDK loop, not the caller's loop.
            await self._run_on_mavsdk_loop(self._system.mavlink_direct.send_message(msg))
        except Exception as e:
            logger.warning(
                f"Rover: failed to send GUIDED ({GUIDED_MODE_NAME}) mode command: {e}",
            )
            return

        start = time.time()
        while self._ts_state.mode.get() != GUIDED_MODE_NAME:
            if time.time() - start > ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S:
                logger.warning(
                    f"Rover: mode switch timeout (current mode={self._ts_state.mode.get()!r}); arming may fail if vehicle is not in GUIDED ({GUIDED_MODE_NAME}) mode",
                )
                return
            await asyncio.sleep(POLLING_DELAY_S)
        logger.info(f"Rover: GUIDED ({GUIDED_MODE_NAME}) mode confirmed")

    def _preflight_wait(self, should_arm: bool) -> None:
        """Wait for pre-arm conditions, setting GUIDED mode first."""
        if not self._in_aerpaw():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._set_guided_mode(),
                    self._mavsdk_loop,
                )
                try:
                    future.result(timeout=ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S + MAVLINK_COMMAND_TIMEOUT_S + 2.0)
                except BaseException:
                    future.cancel()  # do not leave the mode switch running
                    raise
            except Exception as e:
                logger.warning(f"Rover: failed to run _set_guided_mode in preflight: {e}")
        super()._preflight_wait(should_arm)

    async def goto_coordinates(
        self,
        coordinates: util.Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float | None = DEFAULT_GOTO_TIMEOUT_S,
    ) -> None:
        """
        Make the vehicle go to provided coordinates.

        Args:
            coordinates: Target position
            tolerance: Distance in meters to consider destination reached
            target_heading: Ignored for rovers (they can't strafe)
            timeout: Timeout in seconds for mavsdk action to complete
                (default: DEFAULT_GOTO_TIMEOUT_S)

        Raises:
            ValueError: If tolerance is out of acceptable range
            NavigationError: If navigation command fails
        """
        validate_tolerance(tolerance, "tolerance")
        if self.safety is not None:
            ok, msg = self.safety.validate_waypoint_command(self.position, coordinates)
            if not ok:
                raise NavigationError(f"goto rejected by safety checks: {msg}")

        logger.debug(
            f"goto_coordinates(lat={coordinates.lat}, lon={coordinates.lon}, tolerance={tolerance}, target_heading={target_heading}) called",
        )
        await self.await_ready_to_move()
        await self._stop()
        # goto_location takes AMSL; rovers send the home AMSL altitude.
        self._require_movement_fix(NavigationError)

        self._ready_to_move = lambda _: False

        if self._mission_start_time is None:
            self._mission_start_time = time.time()

        from aerpawlib.cli.progress_bar import update_progress

        try:
            update_progress(state="Navigating")
            logger.debug(f"Navigating to: lat={coordinates.lat}, lon={coordinates.lon}")
            await self._run_on_mavsdk_loop(
                self._system.action.goto_location(
                    coordinates.lat,
                    coordinates.lon,
                    self.home_amsl,  # Rovers use home altitude
                    0,  # Heading
                ),
            )

            self._ready_to_move = lambda s: coordinates.ground_distance(s.position) <= tolerance

            logger.debug(f"Waiting to reach destination (tolerance={tolerance}m)...")
            await self._wait_for_arrival(
                timeout,
                f"Rover failed to reach destination {coordinates} within {timeout}s",
            )
            logger.debug(
                f"Arrived at destination, distance: {coordinates.ground_distance(self.position)}m",
            )
        except ActionError as e:
            logger.error(f"Goto failed: {e}")
            self._ready_to_move = lambda _: True
            raise NavigationError(str(e), original_error=e) from e
        except TimeoutError as e:
            logger.error(f"Goto timed out: {e}")
            self._ready_to_move = lambda _: True
            raise NavigationError(str(e), original_error=e) from e
        except BaseException:
            self._ready_to_move = lambda _: True
            raise
        finally:
            update_progress(state="")

    async def _stop(self) -> None:
        """Stop rover velocity control if it is running."""
        await super()._stop()
        self._velocity_generation += 1
        if self._velocity_active:
            self._velocity_active = False
            try:
                await self._send_rover_stop()
            except Exception as e:
                logger.debug("Rover velocity stop failed: %s", e)

    async def _send_rover_stop(self) -> None:
        """Hold the current heading at speed 0 without leaving GUIDED."""
        from aerpawlib._internal.mavlink_ids import make_rover_stop_message, resolve_mav_sysid

        msg = make_rover_stop_message(resolve_mav_sysid(self._system), self.heading)
        await self._run_on_mavsdk_loop(self._system.mavlink_direct.send_message(msg))

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """Set rover velocity in GUIDED mode.

        Streams SET_POSITION_TARGET_LOCAL_NED velocity setpoints; ArduRover
        steers toward the vector's direction. The vertical component is
        ignored since rovers are ground vehicles. Stopping sends a speed-0
        setpoint at the current heading, so the rover never leaves GUIDED
        (MAVSDK offboard is not used: offboard.stop() switches to HOLD, which
        the AERPAW C-VM filter rejects). Works on the AERPAW testbed.

        Args:
            velocity_vector: Desired velocity as a NED vector (m/s). Down
                component is ignored.
            global_relative: If True (default), the vector is in the global NED
                frame. If False, the vector is relative to the rover's current
                heading and is rotated before being sent.
            duration: If provided, hold the velocity for this many seconds then
                stop. If None, the velocity loop runs until the next movement
                command.

        Raises:
            VelocityError: If the velocity setpoint cannot be sent.
        """
        from aerpawlib._internal.mavlink_ids import make_rover_velocity_message, resolve_mav_sysid

        await self.await_ready_to_move()
        self._velocity_generation += 1
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S + 0.05)

        if not global_relative:
            velocity_vector = velocity_vector.rotate_by_angle(-self.heading)

        if self._event_log:
            self._event_log.log_event(
                "command",
                type="set_velocity",
                north_m_s=velocity_vector.north,
                east_m_s=velocity_vector.east,
                down_m_s=0.0,
                global_relative=global_relative,
                duration_s=duration,
            )

        msg = make_rover_velocity_message(
            resolve_mav_sysid(self._system),
            velocity_vector.north,
            velocity_vector.east,
        )
        try:
            await self._run_on_mavsdk_loop(self._system.mavlink_direct.send_message(msg))
        except Exception as e:
            raise VelocityError(str(e), original_error=e) from e
        self._velocity_active = True

        self._ready_to_move = lambda _: True
        gen = self._velocity_generation
        target_end = time.monotonic() + duration if duration is not None else None

        async def _velocity_helper() -> None:
            """Resend the setpoint until timeout or replacement."""
            try:
                while self._velocity_generation == gen:
                    if target_end is not None and time.monotonic() > target_end:
                        self._velocity_generation += 1
                        self._velocity_active = False
                        await self._send_rover_stop()
                        return
                    await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)
                    if self._velocity_generation != gen:
                        return
                    await self._run_on_mavsdk_loop(self._system.mavlink_direct.send_message(msg))
            except Exception as e:
                logger.error("Rover velocity helper error: %s", e)
                if self._velocity_generation == gen:
                    self._velocity_active = False
                    with contextlib.suppress(Exception):
                        await self._send_rover_stop()

        task = asyncio.create_task(_velocity_helper())
        self._command_tasks.append(task)
