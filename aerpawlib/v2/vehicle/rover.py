"""
Rover vehicle for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from mavsdk.action import ActionError

from ..constants import (
    ARMABLE_STATUS_LOG_INTERVAL_S,
    ARMABLE_TIMEOUT_S,
    ARMING_SEQUENCE_DELAY_S,
    DEFAULT_GOTO_TIMEOUT_S,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
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

    async def _initialize_prearm(self, should_postarm_init: bool = True) -> None:
        """Wait for pre-arm conditions (GPS fix, armable). Call before run."""
        self._should_postarm_init = should_postarm_init
        logger.info("Rover: _initialize_prearm started (waiting for armable)")
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
        logger.info("Rover: _initialize_prearm done (armable or timeout)")

    async def _initialize_postarm(self) -> None:
        """Arm and prepare rover for mission (auto-arm after GPS fix)."""
        if not self._should_postarm_init:
            logger.debug("Rover: _initialize_postarm skipped (_should_postarm_init=False)")
            return
        logger.info("Rover: _initialize_postarm (waiting for armable, GPS fix, arming)")
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
        logger.info("Rover: _initialize_postarm done (armed, home position set)")

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
        try:
            await self._system.action.hold()
            await _wait_for_condition(
                lambda: self.mode == "HOLD",
                timeout=5.0,
                timeout_message="HOLD mode did not engage",
            )
        except (ActionError, TimeoutError) as e:
            logger.warning(f"Rover: Could not set HOLD before goto: {e}")
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
