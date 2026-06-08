"""
Rover vehicle for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

from mavsdk.action import ActionError
from mavsdk.mavlink_direct import MavlinkMessage
from mavsdk.offboard import OffboardError, VelocityNedYaw
from pymavlink import mavutil

from aerpawlib.v2.constants import (
    DEFAULT_GOTO_TIMEOUT_S,
    GOTO_POLL_INTERVAL_S,
    MAVLINK_MSG_COMMAND_LONG,
    OFFBOARD_STOP_SETTLE_DELAY_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    VELOCITY_LOOP_HANDOFF_DELAY_S,
    VELOCITY_UPDATE_DELAY_S,
)
from aerpawlib.v2.exceptions import NavigationError, VelocityError
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.types import Coordinate, VectorNED

from .base import Vehicle, _wait_for_condition
from .connection_helpers import _validate_tolerance
from .navigation import start_nonblocking_goto, wait_for_blocking_goto
from .task import VehicleTask

logger = get_logger(LogComponent.ROVER)

# Ground rover navigation uses horizontal distance only for arrival checks.
DEFAULT_ROVER_POSITION_TOLERANCE_M = 2.1


class Rover(Vehicle):
    """Rover implementation for ground vehicles."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise rover movement state."""
        super().__init__(*args, **kwargs)

    @property
    def _default_goto_tolerance(self) -> float:
        return DEFAULT_ROVER_POSITION_TOLERANCE_M

    def _vehicle_type_label(self) -> str:
        return "rover"

    async def _preflight_wait(self, should_arm: bool = True) -> None:
        """Switch to GUIDED mode, then wait for armable state."""
        self._will_arm = should_arm
        await self._set_guided_mode()
        await self._wait_for_armable(log_prefix="Rover: ")

    async def _pre_auto_arm(self) -> None:
        await self._set_guided_mode()

    async def _set_guided_mode(self) -> None:
        """Switch the rover to GUIDED mode before arming.

        ArduPilot Rover requires GUIDED mode to accept arm commands via
        MAVLink. MAVSDK does not expose a direct flight-mode setter for
        ArduPilot due to incompatibility with its custom mode system, so
        this method sends a raw ``MAV_CMD_DO_SET_MODE`` command through
        ``mavlink_direct`` and waits for the mode telemetry to update.
        """
        if self.mode == "OFFBOARD":
            logger.debug(
                "Rover: already in GUIDED (OFFBOARD) mode, skipping mode switch",
            )
            return
        logger.info(
            f"Rover: switching to GUIDED (OFFBOARD) mode (current mode={self.mode!r})",
        )
        try:
            # COMMAND_LONG payload for MAV_CMD_DO_SET_MODE -> GUIDED.
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

            # Wrap the payload for mavlink_direct transmission.
            msg = MavlinkMessage(
                system_id=1,
                component_id=1,
                target_system_id=1,
                target_component_id=1,
                message_name=MAVLINK_MSG_COMMAND_LONG,
                fields_json=json.dumps(fields),
            )

            # Send directly to the flight controller.
            await self._system.mavlink_direct.send_message(msg)
        except Exception as e:
            logger.warning(f"Rover: failed to send GUIDED (OFFBOARD) mode command: {e}")
            return

        try:
            await _wait_for_condition(
                lambda: self.mode == "OFFBOARD",
                timeout=ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
                timeout_message=(f"Rover did not enter GUIDED (OFFBOARD) mode within {ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S}s"),
            )
            logger.info("Rover: GUIDED (OFFBOARD) mode confirmed")
        except TimeoutError:
            logger.warning(
                f"Rover: mode switch timeout (current mode={self.mode!r}); arming may fail if vehicle is not in GUIDED (OFFBOARD) mode",
            )

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Navigate to a target coordinate using ground-distance arrival.

        Args:
            coordinates: Target position.
            tolerance: Arrival tolerance in metres (ground distance).
            target_heading: Unused for rovers; accepted for API parity.
            timeout: Maximum seconds to wait for arrival.
            blocking: If False, returns a VehicleTask immediately.

        Returns:
            None when blocking=True; VehicleTask when blocking=False.

        Raises:
            NavigationError: If command dispatch fails or arrival times out.
        """
        _validate_tolerance(tolerance, "tolerance")
        await self.await_ready_to_move()
        self._ready_to_move = lambda _: False
        logger.debug(
            "Rover: sending goto_location(%.6f, %.6f) command",
            coordinates.lat,
            coordinates.lon,
        )
        try:
            await self._system.action.goto_location(
                coordinates.lat,
                coordinates.lon,
                self.home_amsl,
                0,
            )
        except ActionError as e:
            logger.error(f"Rover: goto_coordinates failed (ActionError): {e}")
            raise NavigationError(str(e), original_error=e) from e

        self._ready_to_move = lambda s: coordinates.ground_distance(s.position) <= tolerance

        if blocking:
            try:
                await wait_for_blocking_goto(
                    self,
                    coordinates,
                    distance_fn=lambda: coordinates.ground_distance(self.position),
                    tolerance=tolerance,
                    timeout=timeout,
                    log_prefix="Rover",
                )
                return None
            except TimeoutError as e:
                logger.error(f"Rover: goto_coordinates failed (timeout): {e}")
                raise NavigationError(str(e), original_error=e) from e

        async def _on_cancel() -> None:
            try:
                if not self.closed and self._system is not None:
                    await self._system.action.hold()
            except Exception as exc:
                logger.warning(f"Rover: _on_cancel hold failed: {exc}")

        return start_nonblocking_goto(
            self,
            coordinates,
            distance_fn=lambda: coordinates.ground_distance(self.position),
            tolerance=tolerance,
            timeout=timeout,
            on_cancel=_on_cancel,
            log_prefix="Rover",
            progress_poll_interval=GOTO_POLL_INTERVAL_S,
        )

    async def set_velocity(
        self,
        velocity_vector: VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """Set rover velocity using MAVSDK offboard mode.

        ArduRover supports velocity control in GUIDED mode via offboard
        SET_POSITION_TARGET_LOCAL_NED. The vertical component is always zeroed
        since rovers are ground vehicles.

        Args:
            velocity_vector: Desired velocity as a NED vector (m/s). Down
                component is ignored.
            global_relative: If True (default), the vector is in the global NED
                frame. If False, the vector is rotated by the rover's heading
                before being sent.
            duration: Hold velocity for this many seconds then stop. If None,
                the velocity loop runs until the next movement command.

        Raises:
            VelocityError: If offboard mode cannot be started.
        """
        await self.await_ready_to_move()
        self._offboard.stop_velocity_loop()
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S + VELOCITY_LOOP_HANDOFF_DELAY_S)

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
        try:
            await self._system.offboard.set_velocity_ned(
                VelocityNedYaw(
                    velocity_vector.north,
                    velocity_vector.east,
                    0,  # Vertical command is always zero for ground vehicles.
                    0,
                ),
            )
            with contextlib.suppress(OffboardError):
                await self._system.offboard.start()

            self._offboard.mark_active()
            self._ready_to_move = lambda _: True
            self._offboard.velocity_loop_active = True
            target_end = time.monotonic() + duration if duration is not None else None

            async def _velocity_helper() -> None:
                """Keep the active velocity command alive and stop on timeout."""
                try:
                    while self._offboard.velocity_loop_active:
                        if target_end and time.monotonic() > target_end:
                            self._offboard.stop_velocity_loop()
                            try:
                                await self._system.offboard.set_velocity_ned(
                                    VelocityNedYaw(0, 0, 0, 0),
                                )
                                await asyncio.sleep(OFFBOARD_STOP_SETTLE_DELAY_S)
                                await self._system.offboard.stop()
                            except Exception as e:
                                logger.debug(
                                    "Rover velocity stop cleanup failed: %s",
                                    e,
                                )
                            return
                        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)
                except Exception as e:
                    logger.error("Rover velocity helper error: %s", e)
                    with contextlib.suppress(Exception):
                        await self._system.offboard.stop()

            vel_task = asyncio.ensure_future(_velocity_helper())
            self._command_tasks.append(vel_task)

        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e) from e
