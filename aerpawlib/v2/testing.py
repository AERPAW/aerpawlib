"""
Test helpers for aerpawlib v2.

Provides mock vehicle and utilities for testing.
"""

from __future__ import annotations

from typing import Optional

from .types import Battery, Coordinate, GPSInfo


class MockVehicle:
    """Minimal mock vehicle for unit tests."""

    def __init__(
        self,
        position: Optional[Coordinate] = None,
        home: Optional[Coordinate] = None,
        armed: bool = False,
        connected: bool = True,
    ):
        """Initialize the mock vehicle with optional pre-set state.

        Args:
            position: Initial position; defaults to NCSU coordinates at ground level.
            home: Home coordinate; defaults to the initial position.
            armed: Whether the vehicle starts armed.
            connected: Whether the vehicle starts in a connected state.
        """
        self._position = position or Coordinate(35.727436, -78.696587, 0)
        self._home = home or self._position
        self._armed = armed
        self._connected = connected
        self._battery = Battery(12.6, 0.0, 100)
        self._gps = GPSInfo(3, 10)
        self._heading = 0.0

    @property
    def connected(self) -> bool:
        """Return whether the mock is considered connected."""
        return self._connected

    @property
    def armed(self) -> bool:
        """Return whether the mock is armed."""
        return self._armed

    @property
    def position(self) -> Coordinate:
        """Return the mock's current position."""
        return self._position

    @property
    def home_coords(self) -> Optional[Coordinate]:
        """Return the mock home coordinate."""
        return self._home

    @property
    def battery(self) -> Battery:
        """Return static mock battery telemetry."""
        return self._battery

    @property
    def gps(self) -> GPSInfo:
        """Return static mock GPS telemetry."""
        return self._gps

    @property
    def heading(self) -> float:
        """Return the mock heading in degrees."""
        return self._heading

    def heartbeat_tick(self) -> None:
        """No-op heartbeat tick required by VehicleProtocol."""
        pass
