"""
Rover vehicle for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from mavsdk.action import ActionError

from ..constants import (
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
)
from ..exceptions import NavigationError
from ..log import LogComponent, get_logger
from ..types import Coordinate
from .base import Vehicle, _validate_tolerance, _wait_for_condition

logger = get_logger(LogComponent.ROVER)

# Rover uses ground distance for tolerance
DEFAULT_ROVER_POSITION_TOLERANCE_M = 2.1


class Rover(Vehicle):
    """Rover implementation for ground vehicles."""

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
    ) -> None:
        """Navigate to coordinates (2D ground). target_heading ignored."""
        logger.info(
            f"Rover: goto_coordinates ({coordinates.lat:.6f}, {coordinates.lon:.6f}) "
            f"tolerance={tolerance}m, timeout={timeout}s"
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
            self._ready_to_move = (
                lambda s: coordinates.ground_distance(s.position) <= tolerance
            )
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
        except ActionError as e:
            logger.error(f"Rover: goto_coordinates failed (ActionError): {e}")
            raise NavigationError(str(e), original_error=e)
        except TimeoutError as e:
            logger.error(f"Rover: goto_coordinates failed (timeout): {e}")
            raise NavigationError(str(e), original_error=e)
