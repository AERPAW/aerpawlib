"""
Geofence utilities for aerpawlib v2.

Extracted from v1 util.
"""

from __future__ import annotations

from typing import Generator, List, Tuple


def read_geofence(file_path: str) -> List[dict]:
    """
    Parse a KML file into a list of lat/lon points.

    Returns:
        List of {'lat': ..., 'lon': ...} dicts.
    """
    from pykml import parser

    with open(file_path, "rb") as f:
        root = parser.fromstring(f.read())
    coords_str = (
        root.Document.Placemark.Polygon.outerBoundaryIs.LinearRing.coordinates.text
    )
    polygon = []
    for s in coords_str.split():
        parts = s.split(",")
        polygon.append({"lon": float(parts[0]), "lat": float(parts[1])})
    return polygon


def inside(lon: float, lat: float, geofence: List[dict]) -> bool:
    """Check if point (lon, lat) is inside polygon using ray-casting."""
    n = len(geofence)
    inside_flag = False
    j = n - 1
    for i in range(n):
        loni, lati = geofence[i]["lon"], geofence[i]["lat"]
        lonj, latj = geofence[j]["lon"], geofence[j]["lat"]
        if ((lati > lat) != (latj > lat)) and (
            lon < (lonj - loni) * (lat - lati) / (latj - lati) + loni
        ):
            inside_flag = not inside_flag
        j = i
    return inside_flag


def _lies_on_segment(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> bool:
    """Check if Q lies on segment PR."""
    return (
        (qx <= max(px, rx))
        and (qx >= min(px, rx))
        and (qy <= max(py, ry))
        and (qy >= min(py, ry))
    )


def _orientation(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> int:
    """Orientation of (p, q, r): 0 colinear, 1 clockwise, 2 counterclockwise."""
    val = (qy - py) * (rx - qx) - (qx - px) * (ry - qy)
    if val > 0:
        return 1
    if val < 0:
        return 2
    return 0


def do_intersect(
    px: float, py: float, qx: float, qy: float,
    rx: float, ry: float, sx: float, sy: float,
) -> bool:
    """Check if segment PQ intersects segment RS."""
    o1 = _orientation(px, py, qx, qy, rx, ry)
    o2 = _orientation(px, py, qx, qy, sx, sy)
    o3 = _orientation(rx, ry, sx, sy, px, py)
    o4 = _orientation(rx, ry, sx, sy, qx, qy)
    if (o1 != o2) and (o3 != o4):
        return True
    if (o1 == 0) and _lies_on_segment(px, py, rx, ry, qx, qy):
        return True
    if (o2 == 0) and _lies_on_segment(px, py, sx, sy, qx, qy):
        return True
    if (o3 == 0) and _lies_on_segment(rx, ry, px, py, sx, sy):
        return True
    if (o4 == 0) and _lies_on_segment(rx, ry, qx, qy, sx, sy):
        return True
    return False


def polygon_edges(
    polygon: List[dict],
) -> Generator[Tuple[dict, dict], None, None]:
    """Yield consecutive (p1, p2) edge pairs for polygon."""
    n = len(polygon)
    for i in range(n):
        yield polygon[i], polygon[(i + 1) % n]
