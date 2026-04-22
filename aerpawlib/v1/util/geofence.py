"""
Geofence parsing and polygon geometry helpers for v1.

This module provides KML geofence parsing and geometric predicates used by v1
safety validation, including point-in-polygon and segment intersection checks.

Capabilities:
- Parse KML polygon coordinates into lat/lon vertex dictionaries.
- Determine whether points lie inside configured geofence polygons.
- Detect line-segment intersections for path boundary checks.

Notes:
- CamelCase aliases are kept for backward compatibility; new code should use
  the snake_case function names.
"""

from typing import Dict, List

from pykml import parser


def read_geofence(filePath: str) -> List[Dict]:
    """
    Parse a KML file into a list of lat/lon points.

    Args:
        filePath: Path to the KML file.

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


def readGeofence(filePath: str) -> List[Dict]:
    """Backward-compatible alias for :func:`read_geofence`."""
    return read_geofence(filePath)


def inside(lon: float, lat: float, geofence: List[Dict]) -> bool:
    """
    Determine if a point is inside a polygon using ray-casting.

    Args:
        lon: Longitude of point.
        lat: Latitude of point.
        geofence: List of {'lat': ..., 'lon': ...} points.

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


def lies_on_segment(
    px: float, py: float, qx: float, qy: float, rx: float, ry: float
) -> bool:
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


def liesOnSegment(
    px: float, py: float, qx: float, qy: float, rx: float, ry: float
) -> bool:
    """Backward-compatible alias for :func:`lies_on_segment`."""
    return lies_on_segment(px, py, qx, qy, rx, ry)


def orientation(
    px: float, py: float, qx: float, qy: float, rx: float, ry: float
) -> int:
    """
    Find the orientation of an ordered triplet (p, q, r).

    Args:
        px, py, qx, qy, rx, ry: Coordinates.

    Returns:
        int: 0 if colinear, 1 if clockwise, 2 if counterclockwise.
    """
    val = (float(qy - py) * (rx - qx)) - (float(qx - px) * (ry - qy))
    if val > 0:
        return 1
    elif val < 0:
        return 2
    else:
        return 0


def do_intersect(
    px: float,
    py: float,
    qx: float,
    qy: float,
    rx: float,
    ry: float,
    sx: float,
    sy: float,
) -> bool:
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

    if (o1 != o2) and (o3 != o4):
        return True

    if (o1 == 0) and lies_on_segment(px, py, rx, ry, qx, qy):
        return True
    if (o2 == 0) and lies_on_segment(px, py, sx, sy, qx, qy):
        return True
    if (o3 == 0) and lies_on_segment(rx, ry, px, py, sx, sy):
        return True
    if (o4 == 0) and lies_on_segment(rx, ry, qx, qy, sx, sy):
        return True

    return False


def doIntersect(
    px: float,
    py: float,
    qx: float,
    qy: float,
    rx: float,
    ry: float,
    sx: float,
    sy: float,
) -> bool:
    """Backward-compatible alias for :func:`do_intersect`."""
    return do_intersect(px, py, qx, qy, rx, ry, sx, sy)
