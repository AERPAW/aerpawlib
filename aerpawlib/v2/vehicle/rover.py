"""
Rover vehicle for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from mavsdk.action import ActionError
from mavsdk.mavlink_direct import MavlinkMessage
from mavsdk.offboard import OffboardError, VelocityNedYaw
from pymavlink import mavutil

from ..constants import (
    ARMABLE_STATUS_LOG_INTERVAL_S,
    ARMABLE_TIMEOUT_S,
    ARMING_SEQUENCE_DELAY_S,
    DEFAULT_GOTO_TIMEOUT_S,
    OFFBOARD_STOP_SETTLE_DELAY_S,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    VELOCITY_LOOP_HANDOFF_DELAY_S,
    VELOCITY_UPDATE_DELAY_S,
)
from ..exceptions import NavigationError, VelocityError
from ..log import LogComponent, get_logger
from ..types import Coordinate, VectorNED
from .base import Vehicle, VehicleTask, _validate_tolerance, _wait_for_condition

logger = get_logger(LogComponent.ROVER)

# Ground rover navigation uses horizontal distance only for arrival checks.
DEFAULT_ROVER_POSITION_TOLERANCE_M = 2.1


class Rover(Vehicle):
    """Rover implementation for ground vehicles."""

    async def _preflight_wait(self, should_arm: bool = True) -> None:
        """Wait for pre-arm readiness before mission start.

        The rover is switched into GUIDED/OFFBOARD first, then this method
        waits until the flight controller reports the vehicle as armable or
        until the armable timeout is reached.

        Args:
            should_arm: Whether the vehicle should be armed later during the
                startup sequence.
        """
        self._will_arm = should_arm
        await self._set_guided_mode()
        start = time.monotonic()
        last_log = 0.0
        while not self._state.armable:
            if time.monotonic() - start > ARMABLE_TIMEOUT_S:
                logger.warning(
                    f"Rover: timeout waiting for armable ({ARMABLE_TIMEOUT_S}s). "
                    f"Status: {self._get_health_summary()}"
                )
                break
            if time.monotonic() - last_log > ARMABLE_STATUS_LOG_INTERVAL_S:
                logger.debug(
                    f"Rover: waiting for armable... {self._get_health_summary()}"
                )
                last_log = time.monotonic()
            await asyncio.sleep(POLLING_DELAY_S)

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
                "Rover: already in GUIDED (OFFBOARD) mode, skipping mode switch"
            )
            return
        logger.info(
            f"Rover: switching to GUIDED (OFFBOARD) mode (current mode={self.mode!r})"
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
                message_name="COMMAND_LONG",
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
                timeout_message=f"Rover did not enter GUIDED (OFFBOARD) mode within {ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S}s",
            )
            logger.info("Rover: GUIDED (OFFBOARD) mode confirmed")
        except TimeoutError:
            logger.warning(
                f"Rover: mode switch timeout (current mode={self.mode!r}); "
                "arming may fail if vehicle is not in GUIDED (OFFBOARD) mode"
            )

    async def _arm_vehicle(self) -> None:
        """Arm the rover and confirm mission prerequisites.

        This waits for armable state and a 3D GPS fix, arms the rover, then
        verifies that a home position is available before mission commands run.

        Raises:
            TimeoutError: If armability, GPS lock, or home position readiness
                does not complete within the configured timeout.
        """
        if not self._will_arm:
            logger.debug("Rover: _arm_vehicle skipped (_will_arm=False)")
            return
        await _wait_for_condition(
            lambda: self._state.armable,
            timeout=30.0,
            timeout_message=f"Rover not armable: {self._get_health_summary()}",
        )
        await _wait_for_condition(
            lambda: self.gps.fix_type >= 3,
            timeout=POSITION_READY_TIMEOUT_S,
            timeout_message="Rover: no GPS 3D fix",
        )
        await self.set_armed(True)
        await asyncio.sleep(ARMING_SEQUENCE_DELAY_S)
        await _wait_for_condition(
            lambda: self._state.home_coords is not None,
            timeout=5.0,
            timeout_message="Rover: home position not available",
        )

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
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
            raise NavigationError(str(e), original_error=e)

        self._ready_to_move = (
            lambda s: coordinates.ground_distance(s.position) <= tolerance
        )

        if blocking:
            try:
                start = time.monotonic()
                last_log = 0.0
                while not self.done_moving():
                    elapsed = time.monotonic() - start
                    if elapsed > timeout:
                        raise TimeoutError(
                            f"Rover failed to reach destination within {timeout}s"
                        )
                    now = time.monotonic()
                    if now - last_log >= 3.0:
                        dist = coordinates.ground_distance(self.position)
                        logger.debug(
                            "Rover: goto_coordinates progress ground_dist=%.1fm tol=%.1fm elapsed=%.0fs",
                            dist,
                            tolerance,
                            elapsed,
                        )
                        last_log = now
                    await asyncio.sleep(0.05)
                return None
            except TimeoutError as e:
                logger.error(f"Rover: goto_coordinates failed (timeout): {e}")
                raise NavigationError(str(e), original_error=e)

        # Non-blocking mode tracks completion and progress in a task handle.
        handle = VehicleTask()
        logger.debug("Rover: goto_coordinates returning non-blocking VehicleTask")

        async def _on_cancel() -> None:
            try:
                if not self._closed and self._system is not None:
                    await self._system.action.hold()
            except Exception as exc:
                logger.warning(f"Rover: _on_cancel hold failed: {exc}")

        handle.set_on_cancel(_on_cancel)

        initial_dist = coordinates.ground_distance(self.position)

        async def _wait_arrival() -> None:
            try:
                await _wait_for_condition(
                    lambda: self.done_moving() or handle.is_cancelled(),
                    timeout=timeout,
                )
                if handle.is_cancelled():
                    handle.set_complete()
                    return
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
                d = coordinates.ground_distance(self.position)
                if initial_dist > 0:
                    p = 1.0 - (d / initial_dist)
                    handle.set_progress(max(0.0, min(1.0, p)))
                now = time.monotonic()
                if now - last_log >= 5.0:
                    logger.debug(
                        "Rover: goto_coordinates (non-blocking) ground_dist=%.1fm progress=%.0f%%",
                        d,
                        handle.progress * 100,
                    )
                    last_log = now
                await asyncio.sleep(0.2)

        t1 = asyncio.create_task(_wait_arrival())
        t2 = asyncio.create_task(_progress_updater())
        self._command_tasks.extend([t1, t2])
        return handle

    async def goto_north(
        self,
        meters: float,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` north from current position."""
        target = self.position + VectorNED(meters, 0, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_east(
        self,
        meters: float,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` east from current position."""
        target = self.position + VectorNED(0, meters, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_south(
        self,
        meters: float,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` south from current position."""
        target = self.position + VectorNED(-meters, 0, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_west(
        self,
        meters: float,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go ``meters`` west from current position."""
        target = self.position + VectorNED(0, -meters, 0)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_ned(
        self,
        north: float,
        east: float,
        down: float = 0,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Go by NED offset from current position.

        Args:
            north: North component in metres (positive = north).
            east: East component in metres (positive = east).
            down: Ignored for rovers (ground vehicles).
            tolerance: Arrival tolerance in metres.
            timeout: Maximum seconds to wait for arrival.
            blocking: If True (default), await arrival before returning.
        """
        target = self.position + VectorNED(north, east, down)
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_bearing(
        self,
        bearing_deg: float,
        distance_m: float,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Drive along ``bearing_deg`` for ``distance_m`` metres from current position.

        Bearing: 0=north, 90=east, 180=south, 270=west.
        """
        v = VectorNED(distance_m, 0, 0).rotate_by_angle(-bearing_deg)
        target = self.position + v
        return await self.goto_coordinates(
            target,
            tolerance=tolerance,
            timeout=timeout,
            blocking=blocking,
        )

    _velocity_loop_active: bool = False

    async def set_velocity(
        self,
        velocity_vector: VectorNED,
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
                frame. If False, the vector is rotated by the rover's heading
                before being sent.
            duration: Hold velocity for this many seconds then stop. If None,
                the velocity loop runs until the next movement command.

        Raises:
            VelocityError: If offboard mode cannot be started.
        """
        await self.await_ready_to_move()
        self._velocity_loop_active = False
        # Give any previous helper loop time to observe the stop flag.
        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S + VELOCITY_LOOP_HANDOFF_DELAY_S)

        if not global_relative:
            velocity_vector = velocity_vector.rotate_by_angle(-self.heading)

        try:
            await self._system.offboard.set_velocity_ned(
                VelocityNedYaw(
                    velocity_vector.north,
                    velocity_vector.east,
                    0,  # Vertical command is always zero for ground vehicles.
                    0,
                )
            )
            try:
                await self._system.offboard.start()
            except OffboardError:
                pass

            self._ready_to_move = lambda _: True
            self._velocity_loop_active = True
            target_end = time.monotonic() + duration if duration is not None else None

            async def _velocity_helper() -> None:
                """Keep the active velocity command alive and stop on timeout."""
                try:
                    while self._velocity_loop_active:
                        if target_end and time.monotonic() > target_end:
                            self._velocity_loop_active = False
                            try:
                                await self._system.offboard.set_velocity_ned(
                                    VelocityNedYaw(0, 0, 0, 0)
                                )
                                await asyncio.sleep(OFFBOARD_STOP_SETTLE_DELAY_S)
                                await self._system.offboard.stop()
                            except Exception as e:
                                logger.debug(
                                    "Rover velocity stop cleanup failed: %s", e
                                )
                            return
                        await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)
                except Exception as e:
                    logger.error("Rover velocity helper error: %s", e)
                    try:
                        await self._system.offboard.stop()
                    except Exception:
                        pass

            vel_task = asyncio.ensure_future(_velocity_helper())
            self._command_tasks.append(vel_task)

        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e)
