"""
Protocols for aerpawlib v2 API.

Used for testing, mocking, and avoiding circular imports.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .types import Battery, Coordinate, GPSInfo, VectorNED


@runtime_checkable
class GPSProtocol(Protocol):
    """Protocol for GPS-like objects."""

    @property
    def fix_type(self) -> int:
        ...

    @property
    def satellites_visible(self) -> int:
        ...


@runtime_checkable
class VehicleProtocol(Protocol):
    """Protocol for vehicle-like objects (ConnectionHandler dependency)."""

    @property
    def connected(self) -> bool:
        ...

    @property
    def armed(self) -> bool:
        ...

    @property
    def position(self) -> Coordinate:
        ...

    @property
    def home_coords(self) -> Optional[Coordinate]:
        ...

    @property
    def battery(self) -> Battery:
        ...

    @property
    def gps(self) -> GPSInfo:
        ...

    @property
    def heading(self) -> float:
        ...

    def heartbeat_tick(self) -> None:
        """Called when telemetry indicates heartbeat received."""
        ...
