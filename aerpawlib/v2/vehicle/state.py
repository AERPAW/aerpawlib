"""
Vehicle state for aerpawlib v2.

Plain attributes updated by telemetry (no ThreadSafeValue).
"""

from __future__ import annotations

from typing import Optional

from ..types import Attitude, Battery, Coordinate, GPSInfo, VectorNED


class VehicleState:
    """Mutable state updated by telemetry subscriptions."""

    def __init__(self) -> None:
        # Position
        self._position_lat: float = 0.0
        self._position_lon: float = 0.0
        self._position_alt: float = 0.0
        self._position_abs_alt: float = 0.0
        # Velocity
        self._velocity_ned: VectorNED = VectorNED(0, 0, 0)
        # Attitude / heading
        self._attitude: Attitude = Attitude(0.0, 0.0, 0.0)
        self._heading_deg: float = 0.0
        # Battery
        self._battery: Battery = Battery(0.0, 0.0, 0)
        # GPS
        self._gps: GPSInfo = GPSInfo(0, 0)
        # Home
        self._home: Optional[Coordinate] = None
        self._home_abs_alt: float = 0.0
        # Armed / mode
        self._armed: bool = False
        self._armable: bool = False
        self._mode: str = "UNKNOWN"
        self._last_arm_time: float = 0.0
        self._armed_telemetry_received: bool = False

    @property
    def position(self) -> Coordinate:
        return Coordinate(
            self._position_lat, self._position_lon, self._position_alt
        )

    @property
    def home_coords(self) -> Optional[Coordinate]:
        return self._home

    @property
    def home_amsl(self) -> float:
        return self._home_abs_alt

    @property
    def velocity(self) -> VectorNED:
        return self._velocity_ned

    @property
    def heading(self) -> float:
        return self._heading_deg % 360

    @property
    def attitude(self) -> Attitude:
        return self._attitude

    @property
    def battery(self) -> Battery:
        return self._battery

    @property
    def gps(self) -> GPSInfo:
        return self._gps

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def armable(self) -> bool:
        return self._armable

    @property
    def mode(self) -> str:
        return self._mode
