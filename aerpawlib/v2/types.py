"""
Types for aerpawlib v2 API.

Dataclasses for Coordinate, VectorNED, Battery, GPSInfo, Attitude.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class VectorNED:
    """
    Displacement in NED (North, East, Down) coordinates, meters.
    """

    north: float
    east: float
    down: float = 0.0

    def rotate_by_angle(self, angle_deg: float) -> "VectorNED":
        """Rotate by angle in degrees (counterclockwise from above)."""
        rads = angle_deg / 180 * math.pi
        east = self.east * math.cos(rads) - self.north * math.sin(rads)
        north = self.east * math.sin(rads) + self.north * math.cos(rads)
        return VectorNED(north, east, self.down)

    def hypot(self, ignore_down: bool = False) -> float:
        """Magnitude in meters."""
        if ignore_down:
            return math.hypot(self.north, self.east)
        return math.sqrt(self.north**2 + self.east**2 + self.down**2)

    def norm(self) -> "VectorNED":
        """Unit vector in same direction."""
        h = self.hypot()
        if h == 0:
            return VectorNED(0, 0, 0)
        return VectorNED(self.north / h, self.east / h, self.down / h)

    def __add__(self, o: "VectorNED") -> "VectorNED":
        return VectorNED(
            self.north + o.north, self.east + o.east, self.down + o.down
        )

    def __sub__(self, o: "VectorNED") -> "VectorNED":
        return VectorNED(
            self.north - o.north, self.east - o.east, self.down - o.down
        )

    def __mul__(self, scalar: float) -> "VectorNED":
        return VectorNED(self.north * scalar, self.east * scalar, self.down * scalar)

    __rmul__ = __mul__


@dataclass
class Coordinate:
    """
    Absolute point in WGS84 space.
    """

    lat: float
    lon: float
    alt: float = 0.0

    def ground_distance(self, other: "Coordinate") -> float:
        """Horizontal distance in meters."""
        if not isinstance(other, Coordinate):
            raise TypeError()
        other = Coordinate(other.lat, other.lon, self.alt)
        return self.distance(other)

    def distance(self, other: "Coordinate") -> float:
        """3D distance in meters (Haversine + altitude)."""
        if not isinstance(other, Coordinate):
            raise TypeError()
        d2r = math.pi / 180
        dlon = (other.lon - self.lon) * d2r
        dlat = (other.lat - self.lat) * d2r
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(self.lat * d2r)
            * math.cos(other.lat * d2r)
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        d_ground = 6378.137 * c * 1000  # km to m
        return math.hypot(d_ground, other.alt - self.alt)

    def bearing(self, other: "Coordinate", wrap_360: bool = True) -> float:
        """Bearing to other in degrees."""
        if not isinstance(other, Coordinate):
            raise TypeError()
        d_lat = other.lat - self.lat
        d_lon = other.lon - self.lon
        if abs(d_lat) < 1e-10 and abs(d_lon) < 1e-10:
            return 0.0
        bearing = 90 + math.atan2(-d_lat, d_lon) * 57.2957795
        if wrap_360:
            bearing %= 360
        return bearing

    def __add__(self, o: VectorNED) -> "Coordinate":
        if not isinstance(o, VectorNED):
            raise TypeError()
        earth_radius = 6378137.0
        d_lat = o.north / earth_radius
        d_lon = o.east / (earth_radius * math.cos(math.pi * self.lat / 180))
        return Coordinate(
            self.lat + d_lat * 180 / math.pi,
            self.lon + d_lon * 180 / math.pi,
            self.alt + (-o.down),
        )

    def __sub__(self, o: "VectorNED | Coordinate") -> "Coordinate | VectorNED":
        if isinstance(o, VectorNED):
            return self + VectorNED(-o.north, -o.east, -o.down)
        if isinstance(o, Coordinate):
            lat_mid = (self.lat + o.lat) * math.pi / 360
            d_lat = self.lat - o.lat
            d_lon = self.lon - o.lon
            return VectorNED(
                d_lat
                * (
                    111132.954
                    - 559.822 * math.cos(2 * lat_mid)
                    + 1.175 * math.cos(4 * lat_mid)
                ),
                d_lon * (111132.954 * math.cos(lat_mid)),
                o.alt - self.alt,
            )
        raise TypeError()

    def to_json(self) -> str:
        """JSON representation."""
        return json.dumps({"lat": self.lat, "lon": self.lon, "alt": self.alt})


@dataclass
class Battery:
    """Battery telemetry."""

    voltage: float
    current: float
    level: int  # 0-100


@dataclass
class GPSInfo:
    """GPS telemetry."""

    fix_type: int  # 0-1: no fix, 2: 2D, 3: 3D
    satellites_visible: int


@dataclass
class Attitude:
    """Attitude (roll, pitch, yaw in radians)."""

    roll: float
    pitch: float
    yaw: float
