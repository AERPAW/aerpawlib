"""
Rover vehicle for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
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
            logger.warning(f"Could not set HOLD: {e}")
        self._ready_to_move = lambda _: False
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
            await _wait_for_condition(
                lambda: self.done_moving(),
                timeout=timeout,
                timeout_message=f"Rover failed to reach destination within {timeout}s",
            )
        except ActionError as e:
            raise NavigationError(str(e), original_error=e)
        except TimeoutError as e:
            raise NavigationError(str(e), original_error=e)
