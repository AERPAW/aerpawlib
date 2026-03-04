"""
Rover vehicle implementation.
"""

import asyncio
import json

from aerpawlib.log import get_logger, LogComponent
import time
from typing import Optional

try:
    from mavsdk.action import ActionError
except ImportError:
    ActionError = Exception

try:
    from mavsdk.offboard import VelocityNedYaw, OffboardError
except ImportError:
    VelocityNedYaw = None  # type: ignore[assignment,misc]
    OffboardError = Exception  # type: ignore[assignment,misc]

from mavsdk.mavlink_direct import MavlinkMessage
from pymavlink import mavutil

from aerpawlib.v1 import util
from aerpawlib.v1.constants import (
    POLLING_DELAY_S,
    DEFAULT_ROVER_POSITION_TOLERANCE_M,
    DEFAULT_GOTO_TIMEOUT_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    VELOCITY_UPDATE_DELAY_S,
)
from aerpawlib.v1.exceptions import (
    NavigationError,
    VelocityError,
)
from aerpawlib.v1.helpers import (
    wait_for_condition,
    validate_tolerance,
)
from aerpawlib.v1.vehicles.core_vehicle import Vehicle

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
            connection_string (str): MAVLink connection string.
            mavsdk_server_port (int): Port for the embedded mavsdk_server gRPC interface.
                Each Vehicle instance should use a unique port to avoid conflicts.
                Defaults to 50051.
        """
        super().__init__(connection_string, mavsdk_server_port=mavsdk_server_port)

    def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode before arming.

        ArduPilot Rover requires GUIDED mode to accept arm commands via
        MAVLink. We send MAV_CMD_DO_SET_MODE directly using mavlink_direct,
        then poll until the flight controller confirms the mode change.
        """
        if self._mode.get() == "OFFBOARD":
            logger.debug(
                "Rover: already in GUIDED (OFFBOARD) mode, skipping mode switch"
            )
            return
        logger.info(
            f"Rover: switching to GUIDED (OFFBOARD) mode "
            f"(current mode={self._mode.get()!r})"
        )
        fields = {
            "target_system": 1,
            "target_component": 1,
            "command": mavutil.mavlink.MAV_CMD_DO_SET_MODE,
            "confirmation": 0,
            "param1": float(mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED),
            "param2": float(ROVER_GUIDED_MODE),
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
            message_name="COMMAND_LONG",
            fields_json=json.dumps(fields),
        )
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._system.mavlink_direct.send_message(msg),
                self._mavsdk_loop,
            )
            future.result(timeout=5.0)
        except Exception as e:
            logger.warning(
                f"Rover: failed to send GUIDED (OFFBOARD) mode command: {e}"
            )
            return

        start = time.time()
        while self._mode.get() != "OFFBOARD":
            if time.time() - start > ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S:
                logger.warning(
                    f"Rover: mode switch timeout "
                    f"(current mode={self._mode.get()!r}); "
                    "arming may fail if vehicle is not in GUIDED (OFFBOARD) mode"
                )
                return
            time.sleep(POLLING_DELAY_S)
        logger.info("Rover: GUIDED (OFFBOARD) mode confirmed")

    def _preflight_wait(self, should_arm: bool) -> None:
        """Wait for pre-arm conditions, setting GUIDED mode first."""
        self._set_guided_mode()
        super()._preflight_wait(should_arm)

    async def goto_coordinates(
        self,
        coordinates: util.Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: Optional[float] = DEFAULT_GOTO_TIMEOUT_S,
    ) -> None:
        """
        Make the vehicle go to provided coordinates.

        Args:
            coordinates: Target position
            tolerance: Distance in meters to consider destination reached
            target_heading: Ignored for rovers (they can't strafe)
            timeout: Timeout in seconds for mavsdk action to complete (default: DEFAULT_GOTO_TIMEOUT_S)

        Raises:
            ValueError: If tolerance is out of acceptable range
            NavigationError: If navigation command fails
        """
        validate_tolerance(tolerance, "tolerance")

        logger.debug(
            f"goto_coordinates(lat={coordinates.lat}, lon={coordinates.lon}, "
            f"tolerance={tolerance}, target_heading={target_heading}) called"
        )
        await self.await_ready_to_move()

        self._ready_to_move = lambda _: False

        if self._mission_start_time is None:
            self._mission_start_time = time.time()

        try:
            logger.debug(
                f"Navigating to: lat={coordinates.lat}, lon={coordinates.lon}"
            )
            await self._run_on_mavsdk_loop(
                self._system.action.goto_location(
                    coordinates.lat,
                    coordinates.lon,
                    self.home_amsl,  # Rovers use home altitude
                    0,  # Heading
                )
            )

            self._ready_to_move = (
                lambda s: coordinates.ground_distance(s.position) <= tolerance
            )

            logger.debug(
                f"Waiting to reach destination (tolerance={tolerance}m)..."
            )
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
                timeout=timeout,
                timeout_message=f"Rover failed to reach destination {coordinates} within {timeout}s",
            )
            logger.debug(
                f"Arrived at destination, distance: {coordinates.ground_distance(self.position)}m"
            )
        except ActionError as e:
            logger.error(f"Goto failed: {e}")
            raise NavigationError(str(e), original_error=e)
        except TimeoutError as e:
            logger.error(f"Goto timed out: {e}")
            raise NavigationError(str(e), original_error=e)

    _velocity_loop_active: bool = False

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: Optional[float] = None,
    ) -> None:
        """Set rover velocity using MAVSDK offboard mode.

        ArduRover supports velocity control in GUIDED mode via offboard
        SET_POSITION_TARGET_LOCAL_NED. The vertical component is always zeroed
        since rovers are ground vehicles.

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
            VelocityError: If offboard mode cannot be started.
        """
        await self.await_ready_to_move()
        self._velocity_loop_active = False
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S + 0.05)

        if not global_relative:
            velocity_vector = velocity_vector.rotate_by_angle(-self.heading)

        try:
            await self._run_on_mavsdk_loop(
                self._system.offboard.set_velocity_ned(
                    VelocityNedYaw(
                        velocity_vector.north,
                        velocity_vector.east,
                        0,  # Rovers don't fly
                        0,
                    )
                )
            )
            try:
                await self._run_on_mavsdk_loop(self._system.offboard.start())
            except OffboardError:
                pass

            self._ready_to_move = lambda _: True
            self._velocity_loop_active = True
            target_end = (
                time.monotonic() + duration if duration is not None else None
            )

            async def _velocity_helper() -> None:
                try:
                    while self._velocity_loop_active:
                        if target_end and time.monotonic() > target_end:
                            self._velocity_loop_active = False
                            try:
                                await self._run_on_mavsdk_loop(
                                    self._system.offboard.set_velocity_ned(
                                        VelocityNedYaw(0, 0, 0, 0)
                                    )
                                )
                                await asyncio.sleep(0.1)
                                await self._run_on_mavsdk_loop(
                                    self._system.offboard.stop()
                                )
                            except Exception as e:
                                logger.debug(
                                    "Rover velocity stop cleanup failed: %s", e
                                )
                            return
                        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)
                except Exception as e:
                    logger.error("Rover velocity helper error: %s", e)
                    try:
                        await self._run_on_mavsdk_loop(
                            self._system.offboard.stop()
                        )
                    except Exception:
                        pass

            asyncio.ensure_future(_velocity_helper())

        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e)
