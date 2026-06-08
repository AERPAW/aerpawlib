"""
.. include:: ../../docs/v2/testing.md
"""

from __future__ import annotations

import asyncio

from aerpawlib.v2.types import Battery, Coordinate, GPSInfo, VectorNED
from aerpawlib.v2.vehicle.connection_state import ConnectionState
from aerpawlib.v2.vehicle.mock_state import default_mock_state
from aerpawlib.v2.vehicle.state import VehicleState


class MockVehicle:
    """Minimal mock vehicle for unit tests implementing VehicleProtocol."""

    def __init__(
        self,
        position: Coordinate | None = None,
        home: Coordinate | None = None,
        *,
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
        self._state: VehicleState = default_mock_state()
        if position is not None:
            self._state.update_position(position.lat, position.lon, position.alt, 0.0)
        if home is not None:
            self._state.update_home(home.lat, home.lon, home.alt, 0.0)
        elif position is not None:
            self._state.update_home(position.lat, position.lon, position.alt, 0.0)
        if armed:
            self._state.update_armed(True)
        self._connection = ConnectionState(
            link_alive=connected,
            closed=not connected,
        )
        if connected:
            self._connection.record_telemetry()

    @property
    def connected(self) -> bool:
        """Return whether the mock is considered connected."""
        return self._connection.connected

    @property
    def closed(self) -> bool:
        """Return whether the mock session is closed."""
        return self._connection.closed

    @property
    def armed(self) -> bool:
        """Return whether the mock is armed."""
        return self._state.armed

    @property
    def position(self) -> Coordinate:
        """Return the mock's current position."""
        return self._state.position

    @property
    def home_coords(self) -> Coordinate | None:
        """Return the mock home coordinate."""
        return self._state.home_coords

    @property
    def battery(self) -> Battery:
        """Return static mock battery telemetry."""
        return self._state.battery

    @property
    def gps(self) -> GPSInfo:
        """Return static mock GPS telemetry."""
        return self._state.gps

    @property
    def heading(self) -> float:
        """Return the mock heading in degrees."""
        return self._state.heading

    @property
    def velocity(self) -> VectorNED:
        """Return the mock NED velocity."""
        return self._state.velocity

    @property
    def attitude(self):
        """Return the mock attitude."""
        return self._state.attitude

    @property
    def mode(self) -> str:
        """Return the mock flight mode."""
        return self._state.mode

    @property
    def armable(self) -> bool:
        """Return whether the mock reports armable."""
        return self._state.armable

    def heartbeat_tick(self) -> None:
        """Record telemetry activity."""
        self._connection.record_telemetry()

    def watch_disconnect(self, timeout: float, **kwargs) -> asyncio.Future:
        """Start disconnect monitoring using the shared ConnectionState."""
        return self._connection.watch_disconnect(timeout, **kwargs)
