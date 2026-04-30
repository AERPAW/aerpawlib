"""
.. include:: ../../docs/v2/types.md
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .constants import (
    EARTH_RADIUS_KM,
    EARTH_RADIUS_M,
    LAT_COEFF_2,
    LAT_COEFF_4,
    LAT_M_PER_DEG,
    RAD_TO_DEG_FACTOR,
)


@dataclass
class VectorNED:
    """
    Displacement in NED (North, East, Down) coordinates, meters.
    """

    north: float
    east: float
    down: float = 0.0

    def rotate_by_angle(self, angle_deg: float) -> VectorNED:
        """Rotate the vector by the given angle.

        Args:
            angle_deg: Rotation angle in degrees, counterclockwise when viewed
                from above.

        Returns:
            New VectorNED rotated by angle_deg.
        """
        rads = angle_deg / 180 * math.pi
        east = self.east * math.cos(rads) - self.north * math.sin(rads)
        north = self.east * math.sin(rads) + self.north * math.cos(rads)
        return VectorNED(north, east, self.down)

    def hypot(self, ignore_down: bool = False) -> float:
        """Return the magnitude of the vector in meters.

        Args:
            ignore_down: If True, compute only the horizontal (2D) magnitude.

        Returns:
            Euclidean norm, optionally ignoring the down component.
        """
        if ignore_down:
            return math.hypot(self.north, self.east)
        return math.sqrt(self.north**2 + self.east**2 + self.down**2)

    def norm(self) -> VectorNED:
        """Return the unit vector in the same direction.

        Returns:
            Normalised VectorNED, or VectorNED(0, 0, 0) if magnitude is zero.
        """
        h = self.hypot()
        if h == 0:
            return VectorNED(0, 0, 0)
        return VectorNED(self.north / h, self.east / h, self.down / h)

    def cross_product(self, other: VectorNED) -> VectorNED:
        """Return the cross product of self and other (self × other).

        Args:
            other: The right-hand operand.

        Returns:
            New VectorNED representing the cross product.

        Raises:
            TypeError: If other is not a VectorNED.
        """
        if not isinstance(other, VectorNED):
            raise TypeError()
        return VectorNED(
            self.east * other.down - self.down * other.east,
            self.down * other.north - self.north * other.down,
            self.north * other.east - self.east * other.north,
        )

    def __add__(self, o: VectorNED) -> VectorNED:
        return VectorNED(self.north + o.north, self.east + o.east, self.down + o.down)

    def __sub__(self, o: VectorNED) -> VectorNED:
        return VectorNED(self.north - o.north, self.east - o.east, self.down - o.down)

    def __mul__(self, scalar: float) -> VectorNED:
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

    def ground_distance(self, other: Coordinate) -> float:
        """Return the horizontal (2D) distance to another coordinate in meters.

        Args:
            other: Target coordinate.

        Returns:
            Ground distance in metres, ignoring altitude difference.

        Raises:
            TypeError: If other is not a Coordinate.
        """
        if not isinstance(other, Coordinate):
            raise TypeError()
        other = Coordinate(other.lat, other.lon, self.alt)
        return self.distance(other)

    def distance(self, other: Coordinate) -> float:
        """Return the 3D distance to another coordinate in meters.

        Uses the Haversine formula for ground distance then combines with
        the altitude difference via Pythagoras.

        Args:
            other: Target coordinate.

        Returns:
            3D distance in metres.

        Raises:
            TypeError: If other is not a Coordinate.
        """
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
        d_ground = EARTH_RADIUS_KM * c * 1000  # km to m
        return math.hypot(d_ground, other.alt - self.alt)

    def bearing(self, other: Coordinate, wrap_360: bool = True) -> float:
        """Return the bearing from this coordinate to another in degrees.

        Args:
            other: Target coordinate.
            wrap_360: If True (default), wrap the result to [0, 360).

        Returns:
            Bearing in degrees.

        Raises:
            TypeError: If other is not a Coordinate.
        """
        if not isinstance(other, Coordinate):
            raise TypeError()
        d_lat = other.lat - self.lat
        d_lon = other.lon - self.lon
        if abs(d_lat) < 1e-10 and abs(d_lon) < 1e-10:
            return 0.0
        bearing = 90 + math.atan2(-d_lat, d_lon) * RAD_TO_DEG_FACTOR
        if wrap_360:
            bearing %= 360
        return bearing

    def __add__(self, o: VectorNED) -> Coordinate:
        if not isinstance(o, VectorNED):
            raise TypeError()
        earth_radius = EARTH_RADIUS_M
        d_lat = o.north / earth_radius
        d_lon = o.east / (earth_radius * math.cos(math.pi * self.lat / 180))
        return Coordinate(
            self.lat + d_lat * 180 / math.pi,
            self.lon + d_lon * 180 / math.pi,
            self.alt + (-o.down),
        )

    def __sub__(self, o: VectorNED | Coordinate) -> Coordinate | VectorNED:
        if isinstance(o, VectorNED):
            return self + VectorNED(-o.north, -o.east, -o.down)
        if isinstance(o, Coordinate):
            lat_mid = (self.lat + o.lat) * math.pi / 360
            d_lat = self.lat - o.lat
            d_lon = self.lon - o.lon
            return VectorNED(
                d_lat
                * (
                    LAT_M_PER_DEG
                    - LAT_COEFF_2 * math.cos(2 * lat_mid)
                    + LAT_COEFF_4 * math.cos(4 * lat_mid)
                ),
                d_lon * (LAT_M_PER_DEG * math.cos(lat_mid)),
                o.alt - self.alt,
            )
        raise TypeError()

    def to_json(self) -> str:
        """Return a JSON string representation of the coordinate.

        Returns:
            JSON string with lat, lon, and alt fields.
        """
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
