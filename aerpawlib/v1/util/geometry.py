"""Coordinate and VectorNED types for v1."""

import json
import math
from typing import Tuple, Union

VectorNEDType = "VectorNED"
CoordinateType = "Coordinate"


class VectorNED:
    """
    Representation of a difference between two coordinates.

    Makes use of the NED (North, East, Down) scheme, with units in meters.

    Attributes:
        north: Displacement in the North direction (meters).
        east: Displacement in the East direction (meters).
        down: Displacement in the Down direction (meters).
    """

    north: float
    east: float
    down: float

    def __init__(self, north: float, east: float, down: float = 0) -> None:
        self.north = north
        self.east = east
        self.down = down

    def rotate_by_angle(self, angle: float) -> "VectorNED":
        """
        Rotate the vector by a given angle in the horizontal plane.

        Args:
            angle: The rotation angle in degrees (counterclockwise
                when viewed from above).

        Returns:
            VectorNED: A new VectorNED object representing the rotated displacement.
        """
        rads = angle / 180 * math.pi

        east = self.east * math.cos(rads) - self.north * math.sin(rads)
        north = self.east * math.sin(rads) + self.north * math.cos(rads)

        return VectorNED(north, east, self.down)

    def cross_product(self, o: "VectorNED") -> "VectorNED":
        """
        Calculate the cross product of this vector and another.

        Args:
            o: The other vector.

        Returns:
            VectorNED: The cross product result (self x o).

        Raises:
            TypeError: If 'o' is not a VectorNED object.
        """
        if not isinstance(o, VectorNED):
            raise TypeError()
        return VectorNED(
            self.east * o.down - self.down * o.east,
            self.down * o.north - self.north * o.down,
            self.north * o.east - self.east * o.north,
        )

    def hypot(self, ignore_down: bool = False) -> float:
        """
        Calculate the magnitude (length) of the vector.

        Args:
            ignore_down: If True, calculate only the 2D ground
                distance (North/East). Defaults to False.

        Returns:
            float: The magnitude in meters.
        """
        if ignore_down:
            return math.hypot(self.north, self.east)
        else:
            return math.sqrt(self.north**2 + self.east**2 + self.down**2)

    def norm(self) -> "VectorNED":
        """
        Returns a unit vector in the same direction as this vector.

        Returns:
            VectorNED: A normalized vector with magnitude 1. If this is a zero
                vector, returns another zero vector.
        """
        hypot = self.hypot()
        if hypot == 0:
            return VectorNED(0, 0, 0)
        return (1 / hypot) * self

    def __add__(self, o: "VectorNED") -> "VectorNED":
        if not isinstance(o, VectorNED):
            raise TypeError()
        return VectorNED(self.north + o.north, self.east + o.east, self.down + o.down)

    def __sub__(self, o: "VectorNED") -> "VectorNED":
        if not isinstance(o, VectorNED):
            raise TypeError()
        return VectorNED(self.north - o.north, self.east - o.east, self.down - o.down)

    def __mul__(self, o: Union[float, int]) -> "VectorNED":
        if not (isinstance(o, float) or isinstance(o, int)):
            raise TypeError()
        return VectorNED(self.north * o, self.east * o, self.down * o)

    __rmul__ = __mul__

    def __str__(self) -> str:
        return "(" + ",".join(map(str, [self.north, self.east, self.down])) + ")"


class Coordinate:
    """
    An absolute point in WGS84 space.

    Attributes:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        alt: Altitude in meters relative to home location.
    """

    lat: float
    lon: float
    alt: float

    def __init__(self, lat: float, lon: float, alt: float = 0) -> None:
        self.lat = lat
        self.lon = lon
        self.alt = alt

    def ground_distance(self, other: "Coordinate") -> float:
        """
        Calculate the horizontal distance to another coordinate.

        Args:
            other: The target coordinate.

        Returns:
            float: Ground distance in meters.

        Raises:
            TypeError: If 'other' is not a Coordinate object.
        """
        if not isinstance(other, Coordinate):
            raise TypeError()

        other = Coordinate(other.lat, other.lon, self.alt)
        return self.distance(other)

    def distance(self, other: "Coordinate") -> float:
        """
        Calculate the 3D distance to another coordinate.

        Uses the Haversine formula for ground distance and accounts for altitude.

        Args:
            other: The target coordinate.

        Returns:
            float: 3D distance in meters.

        Raises:
            TypeError: If 'other' is not a Coordinate object.
        """
        if not isinstance(other, Coordinate):
            raise TypeError()

        d2r = math.pi / 180
        dlon = (other.lon - self.lon) * d2r
        dlat = (other.lat - self.lat) * d2r
        a = math.pow(math.sin(dlat / 2), 2) + math.cos(self.lat * d2r) * math.cos(
            other.lat * d2r
        ) * math.pow(math.sin(dlon / 2), 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        d = 6378.137 * c
        return math.hypot(d * 1000, other.alt - self.alt)

    def bearing(self, other: "Coordinate", wrap_360: bool = True) -> float:
        """
        Calculate the bearing (compass angle) to another coordinate.

        Args:
            other: The target coordinate.
            wrap_360: Whether to wrap the result to [0, 360).
                Defaults to True.

        Returns:
            float: Bearing in degrees.

        Raises:
            TypeError: If 'other' is not a Coordinate object.
        """
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
        if isinstance(o, VectorNED):
            north = o.north
            east = o.east
            alt = -o.down
        else:
            raise TypeError()

        earth_radius = 6378137.0
        d_lat = north / earth_radius
        d_lon = east / (earth_radius * math.cos(math.pi * self.lat / 180))
        new_lat = self.lat + (d_lat * 180 / math.pi)
        new_lon = self.lon + (d_lon * 180 / math.pi)

        return Coordinate(new_lat, new_lon, self.alt + alt)

    def __sub__(self, o):
        if isinstance(o, VectorNED):
            return self + VectorNED(-o.north, -o.east, -o.down)
        elif isinstance(o, Coordinate):
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
        else:
            raise TypeError()

    def __str__(self) -> str:
        return f"({self.lat},{self.lon},{self.alt})"

    def to_json(self) -> str:
        """
        Serialize the coordinate to a JSON string.

        Returns:
            str: JSON representation of the lat, lon, and alt.
        """
        return json.dumps(self, default=lambda o: o.__dict__)

    def toJson(self) -> str:
        """Backward-compatible alias for :meth:`to_json`."""
        return self.to_json()


Waypoint = Tuple[
    int, float, float, float, int, float
]
