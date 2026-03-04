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
from pymavlink import mavutil

from ..constants import (
    ARMABLE_STATUS_LOG_INTERVAL_S,
    ARMABLE_TIMEOUT_S,
    ARMING_SEQUENCE_DELAY_S,
    DEFAULT_GOTO_TIMEOUT_S,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
)
from ..exceptions import NavigationError
from ..log import LogComponent, get_logger
from ..types import Coordinate
from .base import Vehicle, VehicleTask, _validate_tolerance, _wait_for_condition

logger = get_logger(LogComponent.ROVER)

# Rover uses ground distance for tolerance
DEFAULT_ROVER_POSITION_TOLERANCE_M = 2.1


class Rover(Vehicle):
    """Rover implementation for ground vehicles."""

    async def _preflight_wait(self, should_arm: bool = True) -> None:
        """Wait for pre-arm conditions (GPS fix, armable). Call before run."""
        self._will_arm = should_arm
        logger.info("Rover: _preflight_wait started (waiting for armable)")
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
                logger.debug(f"Rover: waiting for armable... {self._get_health_summary()}")
                last_log = time.monotonic()
            await asyncio.sleep(POLLING_DELAY_S)
        logger.info("Rover: _preflight_wait done (armable or timeout)")

    async def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode before arming.

        ArduPilot Rover requires GUIDED mode to accept arm commands via
        MAVLink. MAVSDK does not expose a direct flight-mode setter for
        ArduPilot due to incompatibility with its custom mode system, so
        we send the raw MAV_CMD_DO_SET_MODE command via mavlink_passthrough.
        """
        if self.mode == "OFFBOARD":
            logger.debug("Rover: already in GUIDED (OFFBOARD) mode, skipping mode switch")
            return
        logger.info(f"Rover: switching to GUIDED (OFFBOARD) mode (current mode={self.mode!r})")
        try:
            # Build the payload dictionary using your original constants
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

            # Package into the MavlinkMessage object
            msg = MavlinkMessage(
                system_id=1,
                component_id=1,
                target_system_id=1,
                target_component_id=1,
                message_name="COMMAND_LONG",
                fields_json=json.dumps(fields),
            )

            # Send the serialized message directly to the flight controller
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
        """Arm and prepare rover for mission (auto-arm after GPS fix)."""
        if not self._will_arm:
            logger.debug("Rover: _arm_vehicle skipped (_will_arm=False)")
            return
        logger.info("Rover: _arm_vehicle (waiting for armable, GPS fix, arming)")
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
        logger.info("Rover: _arm_vehicle done (armed, home position set)")

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> Optional[VehicleTask]:
        """Navigate to coordinates (2D ground). target_heading ignored.

        Args:
            coordinates: Target position.
            tolerance: Arrival tolerance in metres (ground distance).
            target_heading: Ignored for rovers.
            timeout: Maximum seconds to wait for arrival.
            blocking: If False, returns a VehicleTask immediately.

        Returns:
            None when blocking=True; VehicleTask when blocking=False.
        """
        logger.info(
            f"Rover: goto_coordinates ({coordinates.lat:.6f}, {coordinates.lon:.6f}) "
            f"tolerance={tolerance}m, timeout={timeout}s, blocking={blocking}"
        )
        _validate_tolerance(tolerance, "tolerance")
        await self.await_ready_to_move()
        self._ready_to_move = lambda _: False
        logger.debug("Rover: sending goto_location(%.6f, %.6f) command", coordinates.lat, coordinates.lon)
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
                        raise TimeoutError(f"Rover failed to reach destination within {timeout}s")
                    now = time.monotonic()
                    if now - last_log >= 3.0:
                        dist = coordinates.ground_distance(self.position)
                        logger.debug(
                            "Rover: goto_coordinates progress ground_dist=%.1fm tol=%.1fm elapsed=%.0fs",
                            dist, tolerance, elapsed,
                        )
                        last_log = now
                    await asyncio.sleep(0.05)
                logger.info("Rover: goto_coordinates complete")
            except TimeoutError as e:
                logger.error(f"Rover: goto_coordinates failed (timeout): {e}")
                raise NavigationError(str(e), original_error=e)
            return None

        # Non-blocking: return a VehicleTask
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
                        d, handle.progress * 100,
                    )
                    last_log = now
                await asyncio.sleep(0.2)

        t1 = asyncio.create_task(_wait_arrival())
        t2 = asyncio.create_task(_progress_updater())
        self._command_tasks.extend([t1, t2])
        return handle
