"""
Test helpers for aerpawlib v2.

Provides mock vehicle and utilities for testing.
"""

from __future__ import annotations

from typing import Optional

from .types import Battery, Coordinate, GPSInfo, VectorNED


class MockVehicle:
    """Minimal mock vehicle for unit tests."""

    def __init__(
        self,
        position: Optional[Coordinate] = None,
        home: Optional[Coordinate] = None,
        armed: bool = False,
        connected: bool = True,
    ):
        self._position = position or Coordinate(35.727436, -78.696587, 0)
        self._home = home or self._position
        self._armed = armed
        self._connected = connected
        self._battery = Battery(12.6, 0.0, 100)
        self._gps = GPSInfo(3, 10)
        self._heading = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def position(self) -> Coordinate:
        return self._position

    @property
    def home_coords(self) -> Optional[Coordinate]:
        return self._home

    @property
    def battery(self) -> Battery:
        return self._battery

    @property
    def gps(self) -> GPSInfo:
        return self._gps

    @property
    def heading(self) -> float:
        return self._heading

    def heartbeat_tick(self) -> None:
        pass
