"""
SafetyMonitor for aerpawlib v2.

Emits events and logs only; does not enforce.
Uses await for async callbacks (no fire-and-forget create_task).
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from ..log import LogComponent, get_logger
from ..types import Battery, Coordinate
from .limits import SafetyLimits

logger = get_logger(LogComponent.SAFETY)


class SafetyMonitor:
    """
    Monitors vehicle state against SafetyLimits.

    Emits events and logs only. Does not enforce.
    """

    def __init__(self, limits: SafetyLimits) -> None:
        self._limits = limits
        self._callbacks: list[Callable[[str, str], Awaitable[None]]] = []

    def on_violation(
        self, cb: Callable[[str, str], Awaitable[None]]
    ) -> None:
        """Register async callback (event_type, message)."""
        self._callbacks.append(cb)

    async def _emit(self, event_type: str, message: str) -> None:
        """Emit event to all callbacks. Awaits each (no fire-and-forget)."""
        logger.warning(f"[SafetyMonitor] {event_type}: {message}")
        for cb in self._callbacks:
            await cb(event_type, message)

    async def check_altitude(self, position: Coordinate) -> None:
        """Check altitude against limits."""
        if self._limits.max_altitude_m is not None:
            if position.alt > self._limits.max_altitude_m:
                await self._emit(
                    "ALTITUDE_EXCEEDED",
                    f"Altitude {position.alt}m exceeds max {self._limits.max_altitude_m}m",
                )
        if self._limits.min_altitude_m is not None:
            if position.alt < self._limits.min_altitude_m:
                await self._emit(
                    "ALTITUDE_BELOW_MIN",
                    f"Altitude {position.alt}m below min {self._limits.min_altitude_m}m",
                )

    async def check_battery(self, battery: Battery) -> None:
        """Check battery against limits."""
        if self._limits.min_battery_percent is not None:
            if battery.level < self._limits.min_battery_percent:
                await self._emit(
                    "LOW_BATTERY",
                    f"Battery {battery.level}% below min {self._limits.min_battery_percent}%",
                )
