"""
.. include:: ../../docs/v2/protocols.md
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .types import Battery, Coordinate, GPSInfo


@runtime_checkable
class GPSProtocol(Protocol):
    """Protocol for GPS-like objects."""

    @property
    def fix_type(self) -> int:
        """Return MAVLink GPS fix type (e.g., 0=no fix, 3=3D fix)."""
        ...

    @property
    def satellites_visible(self) -> int:
        """Return the number of visible satellites."""
        ...


@runtime_checkable
class VehicleProtocol(Protocol):
    """Protocol for vehicle-like objects (ConnectionHandler dependency)."""

    @property
    def connected(self) -> bool:
        """Return whether the vehicle connection is active."""
        ...

    @property
    def armed(self) -> bool:
        """Return whether the vehicle is currently armed."""
        ...

    @property
    def position(self) -> Coordinate:
        """Return the latest known global position."""
        ...

    @property
    def home_coords(self) -> Optional[Coordinate]:
        """Return the home coordinate when available."""
        ...

    @property
    def battery(self) -> Battery:
        """Return current battery telemetry."""
        ...

    @property
    def gps(self) -> GPSInfo:
        """Return current GPS telemetry."""
        ...

    @property
    def heading(self) -> float:
        """Return heading in degrees."""
        ...

    def heartbeat_tick(self) -> None:
        """Called when telemetry indicates heartbeat received."""
        ...
