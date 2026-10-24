"""MAVSDK-backed ground vehicle implementation for the v1 API.

See ``aerpawlib.v1.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import TYPE_CHECKING, Any

from aerpawlib.v1.log import LogComponent, get_logger

try:
    from mavsdk.action import ActionError
except ImportError:
    ActionError = Exception

from aerpawlib.v1.constants import (
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_ROVER_POSITION_TOLERANCE_M,
    GUIDED_MODE_NAME,
    MAVLINK_COMMAND_TIMEOUT_S,
    POLLING_DELAY_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
)
from aerpawlib.v1.exceptions import (
    NavigationError,
)
from aerpawlib.v1.helpers import (
    validate_tolerance,
)
from aerpawlib.v1.vehicle.core_vehicle import Vehicle

if TYPE_CHECKING:
    from aerpawlib.v1 import util

logger = get_logger(LogComponent.ROVER)

# Below this a velocity has no direction: ArduRover would steer north
# (atan2(0, 0)), so the rover holds its heading at speed 0 instead.
_STOPPED_SPEED_M_S = 1e-3


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

        sysid = resolve_mav_sysid(self._ts_state.autopilot_sysid.get())
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

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """Set rover velocity in GUIDED mode.

        Streams GUIDED velocity setpoints; ArduRover steers toward the vector's
        direction. The vertical component is ignored since rovers are ground
        vehicles. Returns at once; the velocity holds until `duration` expires
        or the next movement command. Stopping (or a zero vector) holds the
        current heading at speed 0, so the rover never leaves GUIDED and this
        works on the AERPAW testbed, where the C-VM filter limits the speed and
        refuses a velocity that would leave the geofence within a few seconds.

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
            VelocityError: If the velocity or duration is not finite, or the
                setpoint cannot be sent.
        """
        await self._start_velocity(velocity_vector, global_relative, duration)

    def _velocity_setpoint(self, velocity_vector: util.VectorNED) -> Any:
        from aerpawlib._internal.mavlink_ids import make_rover_velocity_message, resolve_mav_sysid

        if math.hypot(velocity_vector.north, velocity_vector.east) < _STOPPED_SPEED_M_S:
            return self._velocity_stop_setpoint()
        return make_rover_velocity_message(resolve_mav_sysid(self._ts_state.autopilot_sysid.get()), velocity_vector.north, velocity_vector.east)

    def _velocity_stop_setpoint(self) -> Any:
        from aerpawlib._internal.mavlink_ids import make_rover_stop_message, resolve_mav_sysid

        return make_rover_stop_message(resolve_mav_sysid(self._ts_state.autopilot_sysid.get()), self.heading)
