"""
Types and functions commonly used throughout the aerpawlib v1 framework.

This version has been updated to remove DroneKit dependencies while
maintaining API compatibility.

@author: Julian Reder (quantumbagel)
"""
import errno
import json
import socket

import math
from typing import List, Tuple

from pykml import parser

from .constants import (
    DEFAULT_WAYPOINT_SPEED,
    PLAN_CMD_TAKEOFF,
    PLAN_CMD_WAYPOINT,
    PLAN_CMD_RTL,
    PLAN_CMD_SPEED,
)


class VectorNED:
    """
    Representation of a difference between two coordinates.

    Makes use of the NED (North, East, Down) scheme, with units in meters.

    Attributes:
        north (float): Displacement in the North direction (meters).
        east (float): Displacement in the East direction (meters).
        down (float): Displacement in the Down direction (meters).
    """

    north: float
    east: float
    down: float

    def __init__(self, north: float, east: float, down: float = 0):
        self.north = north
        self.east = east
        self.down = down

    def rotate_by_angle(self, angle: float):
        """
        Rotate the vector by a given angle in the horizontal plane.

        Args:
            angle (float): The rotation angle in degrees (counterclockwise
                when viewed from above).

        Returns:
            VectorNED: A new VectorNED object representing the rotated displacement.
        """
        rads = angle / 180 * math.pi

        east = self.east * math.cos(rads) - self.north * math.sin(rads)
        north = self.east * math.sin(rads) + self.north * math.cos(rads)

        return VectorNED(north, east, self.down)

    def cross_product(self, o):
        """
        Calculate the cross product of this vector and another.

        Args:
            o (VectorNED): The other vector.

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

    def hypot(self, ignore_down: bool = False):
        """
        Calculate the magnitude (length) of the vector.

        Args:
            ignore_down (bool, optional): If True, calculate only the 2D ground
                distance (North/East). Defaults to False.

        Returns:
            float: The magnitude in meters.
        """
        if ignore_down:
            return math.hypot(self.north, self.east)
        else:
            return math.sqrt(self.north**2 + self.east**2 + self.down**2)

    def norm(self):
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

    def __add__(self, o):
        if not isinstance(o, VectorNED):
            raise TypeError()
        return VectorNED(
            self.north + o.north, self.east + o.east, self.down + o.down
        )

    def __sub__(self, o):
        if not isinstance(o, VectorNED):
            raise TypeError()
        return VectorNED(
            self.north - o.north, self.east - o.east, self.down - o.down
        )

    def __mul__(self, o):
        if not (isinstance(o, float) or isinstance(o, int)):
            raise TypeError()
        return VectorNED(self.north * o, self.east * o, self.down * o)

    __rmul__ = __mul__

    def __str__(self) -> str:
        return (
            "(" + ",".join(map(str, [self.north, self.east, self.down])) + ")"
        )


class Coordinate:
    """
    An absolute point in WGS84 space.

    Attributes:
        lat (float): Latitude in degrees.
        lon (float): Longitude in degrees.
        alt (float): Altitude in meters relative to home location.
    """

    lat: float
    lon: float
    alt: float

    def __init__(self, lat: float, lon: float, alt: float = 0):
        self.lat = lat
        self.lon = lon
        self.alt = alt

    def ground_distance(self, other) -> float:
        """
        Calculate the horizontal distance to another coordinate.

        Args:
            other (Coordinate): The target coordinate.

        Returns:
            float: Ground distance in meters.

        Raises:
            TypeError: If 'other' is not a Coordinate object.
        """
        if not isinstance(other, Coordinate):
            raise TypeError()

        other = Coordinate(other.lat, other.lon, self.alt)
        return self.distance(other)

    def distance(self, other) -> float:
        """
        Calculate the 3D distance to another coordinate.

        Uses the Haversine formula for ground distance and accounts for altitude.

        Args:
            other (Coordinate): The target coordinate.

        Returns:
            float: 3D distance in meters.

        Raises:
            TypeError: If 'other' is not a Coordinate object.
        """
        if not isinstance(other, Coordinate):
            raise TypeError()

        # calculation uses haversine distance
        d2r = math.pi / 180
        dlon = (other.lon - self.lon) * d2r
        dlat = (other.lat - self.lat) * d2r
        a = math.pow(math.sin(dlat / 2), 2) + math.cos(
            self.lat * d2r
        ) * math.cos(other.lat * d2r) * math.pow(math.sin(dlon / 2), 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        d = 6378.137 * c  # WGS84 equatorial radius in km
        return math.hypot(d * 1000, other.alt - self.alt)

    def bearing(self, other, wrap_360: bool = True) -> float:
        """
        Calculate the bearing (compass angle) to another coordinate.

        Args:
            other (Coordinate): The target coordinate.
            wrap_360 (bool, optional): Whether to wrap the result to [0, 360).
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

        # Guard against coincident points where atan2 is undefined/noisy
        if abs(d_lat) < 1e-10 and abs(d_lon) < 1e-10:
            return 0.0  # Default to north when points are coincident

        bearing = 90 + math.atan2(-d_lat, d_lon) * 57.2957795
        if wrap_360:
            bearing %= 360
        return bearing

    def __add__(self, o):
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

    def __str__(self):
        return f"({self.lat},{self.lon},{self.alt})"

    def to_json(self):
        """
        Serialize the coordinate to a JSON string.

        Returns:
            str: JSON representation of the lat, lon, and alt.
        """
        return json.dumps(self, default=lambda o: o.__dict__)

    def toJson(self):
        return self.to_json()


# Waypoint type alias
Waypoint = Tuple[
    int, float, float, float, int, float
]  # command, x, y, z, waypoint_id, speed


def read_from_plan(
    path: str, default_speed: float = DEFAULT_WAYPOINT_SPEED
) -> List[Waypoint]:
    """
    Parse a QGroundControl .plan file into a list of Waypoints.

    Args:
        path (str): Path to the .plan file.
        default_speed (float, optional): Speed to use if none specified in plan.
            Defaults to DEFAULT_WAYPOINT_SPEED.

    Returns:
        List[Waypoint]: A list of extracted waypoint tuples.

    Raises:
        Exception: If the file is not a valid .plan file.
    """
    waypoints = []
    with open(path) as f:
        data = json.load(f)
    if data["fileType"] != "Plan":
        raise Exception("Wrong file type -- use a .plan file.")
    current_speed = default_speed
    for item in data["mission"]["items"]:
        command = item["command"]
        if command in [PLAN_CMD_TAKEOFF, PLAN_CMD_WAYPOINT, PLAN_CMD_RTL]:
            x, y, z = item["params"][4:7]
            waypoint_id = item["doJumpId"]
            waypoints.append((command, x, y, z, waypoint_id, current_speed))
        elif command in [PLAN_CMD_SPEED]:
            current_speed = item["params"][1]
    return waypoints


def get_location_from_waypoint(waypoint: Waypoint) -> Coordinate:
    """
    Extract a Coordinate object from a Waypoint tuple.

    Args:
        waypoint (Waypoint): The waypoint tuple.

    Returns:
        Coordinate: The extracted location.
    """
    return Coordinate(waypoint[1], waypoint[2], waypoint[3])


def read_from_plan_complete(
    path: str, default_speed: float = DEFAULT_WAYPOINT_SPEED
):
    """
    Read a .plan file and return detailed waypoint dictionaries.

    Includes additional fields like wait_for delay.

    Args:
        path (str): Path to the .plan file.
        default_speed (float, optional): Default speed in m/s.

    Returns:
        List[dict]: List of waypoint data dictionaries.
    """
    waypoints = []
    with open(path) as f:
        data = json.load(f)
    if data["fileType"] != "Plan":
        raise Exception("Wrong file type -- use a .plan file.")
    current_speed = default_speed
    for item in data["mission"]["items"]:
        command = item["command"]
        if command in [PLAN_CMD_SPEED]:
            current_speed = item["params"][1]
        elif command in [PLAN_CMD_TAKEOFF, PLAN_CMD_WAYPOINT, PLAN_CMD_RTL]:
            x, y, z = item["params"][4:7]
            waypoint_id = item["doJumpId"]
            delay = item["params"][0]
            waypoints.append(
                {
                    "id": waypoint_id,
                    "command": command,
                    "pos": [x, y, z],
                    "wait_for": delay,
                    "speed": current_speed,
                }
            )
    return waypoints


def read_geofence(filePath):
    """
    Parse a KML file into a list of lat/lon points.

    Args:
        filePath (str): Path to the KML file.

    Returns:
        List[dict]: Points as [{'lat': ..., 'lon': ...}, ...].
    """
    with open(filePath, "rb") as f:
        root = parser.fromstring(f.read())
    coordinates_string = (
        root.Document.Placemark.Polygon.outerBoundaryIs.LinearRing.coordinates.text
    )
    coordinates_list = coordinates_string.split()
    polygon = []
    for str_val in coordinates_list:
        point = {
            "lon": float(str_val.split(",")[0]),
            "lat": float(str_val.split(",")[1]),
        }
        polygon.append(point)
    return polygon


def readGeofence(filePath):
    return read_geofence(filePath)


def inside(lon, lat, geofence):
    """
    Determine if a point is inside a polygon using ray-casting.

    Args:
        lon (float): Longitude of point.
        lat (float): Latitude of point.
        geofence (list): List of {'lat': ..., 'lon': ...} points.

    Returns:
        bool: True if inside, False otherwise.
    """
    inside = False
    i = 0
    j = len(geofence) - 1

    while i < len(geofence):
        loni = geofence[i]["lon"]
        lati = geofence[i]["lat"]
        lonj = geofence[j]["lon"]
        latj = geofence[j]["lat"]

        intersect = ((lati > lat) != (latj > lat)) and (
            lon < (lonj - loni) * (lat - lati) / (latj - lati) + loni
        )
        if intersect:
            inside = not inside
        j = i
        i += 1

    return inside


def lies_on_segment(px, py, qx, qy, rx, ry):
    """
    Check if point Q lies on line segment PR.

    Args:
        px, py: Coords of point P.
        qx, qy: Coords of point Q.
        rx, ry: Coords of point R.

    Returns:
        bool: True if Q is on PR.
    """
    if (
        (qx <= max(px, rx))
        and (qx >= min(px, rx))
        and (qy <= max(py, ry))
        and (qy >= min(py, ry))
    ):
        return True
    return False


def liesOnSegment(px, py, qx, qy, rx, ry):
    return lies_on_segment(px, py, qx, qy, rx, ry)


def orientation(px, py, qx, qy, rx, ry):
    """
    Find the orientation of an ordered triplet (p, q, r).

    Args:
        px, py, qx, qy, rx, ry: Coordinates.

    Returns:
        int: 0 if colinear, 1 if clockwise, 2 if counterclockwise.
    """
    val = (float(qy - py) * (rx - qx)) - (float(qx - px) * (ry - qy))
    if val > 0:
        return 1  # Clockwise
    elif val < 0:
        return 2  # Counterclockwise
    else:
        return 0  # Colinear


def do_intersect(px, py, qx, qy, rx, ry, sx, sy):
    """
    Check if line segment PQ intersects with segment RS.

    Args:
        px, py, qx, qy: Coords of segment PQ.
        rx, ry, sx, sy: Coords of segment RS.

    Returns:
        bool: True if they intersect.
    """
    o1 = orientation(px, py, qx, qy, rx, ry)
    o2 = orientation(px, py, qx, qy, sx, sy)
    o3 = orientation(rx, ry, sx, sy, px, py)
    o4 = orientation(rx, ry, sx, sy, qx, qy)

    # General case
    if (o1 != o2) and (o3 != o4):
        return True

    # Special Cases
    if (o1 == 0) and lies_on_segment(px, py, rx, ry, qx, qy):
        return True
    if (o2 == 0) and lies_on_segment(px, py, sx, sy, qx, qy):
        return True
    if (o3 == 0) and lies_on_segment(rx, ry, px, py, sx, sy):
        return True
    if (o4 == 0) and lies_on_segment(rx, ry, qx, qy, sx, sy):
        return True

    return False


def doIntersect(px, py, qx, qy, rx, ry, sx, sy):
    return do_intersect(px, py, qx, qy, rx, ry, sx, sy)


def is_udp_port_in_use(host: str, port: int) -> bool:
    """
    Check if a local UDP port is in use by trying to bind to it.

    Args:
        host: The local IP address to bind to (e.g., '127.0.0.1', '0.0.0.0', or '::1').
        port: The port number to check.

    Returns:
        True if the port is in use, False otherwise.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                return True
            return True


def is_tcp_port_in_use(host: str, port: int) -> bool:
    """
    Check if a local TCP port is in use by trying to bind to it.

    Args:
        host: The local IP address to bind to (e.g., '127.0.0.1', '0.0.0.0').
        port: The port number to check.

    Returns:
        True if the port is in use, False otherwise.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                return True
            return True
