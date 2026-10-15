"""
.. include:: ../../docs/v2/geofence.md
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pykml import parser

from aerpawlib._internal.kml import polygon_from_kml

from .log import LogComponent, get_logger

if TYPE_CHECKING:
    from collections.abc import Generator

logger = get_logger(LogComponent.VEHICLE)


def read_geofence(file_path: str) -> list[dict]:
    """
    Parse a KML file into a list of lat/lon points.

    Handles any nesting depth (Folder, Placemark, namespaces). The file must
    hold exactly one Polygon with no holes; anything else would be silently
    enforced as a different fence, so it is rejected.

    Returns:
        List of {'lat': ..., 'lon': ...} dicts.

    Raises:
        ValueError: If the KML has no polygon, more than one, holes, or a
            malformed or non-finite coordinate.
    """
    with Path(file_path).open("rb") as f:
        root = parser.fromstring(f.read())
    return polygon_from_kml(root, file_path)


def inside(lon: float, lat: float, geofence: list[dict]) -> bool:
    """Check if point (lon, lat) is inside the polygon using ray-casting.

    Handles degenerate (horizontal) edges safely by skipping
    division-by-zero cases.

    Args:
        lon: Longitude of the point to test.
        lat: Latitude of the point to test.
        geofence: List of {'lat': ..., 'lon': ...} dicts defining the polygon.

    Returns:
        True if the point is inside the polygon.
    """
    n = len(geofence)
    if n < 3:
        return False
    inside_flag = False
    j = n - 1
    for i in range(n):
        loni, lati = geofence[i]["lon"], geofence[i]["lat"]
        lonj, latj = geofence[j]["lon"], geofence[j]["lat"]
        # Skip horizontal edges (latj == lati) to avoid division by zero
        if lati != latj and ((lati > lat) != (latj > lat)):
            x_intersect = (lonj - loni) * (lat - lati) / (latj - lati) + loni
            if lon < x_intersect:
                inside_flag = not inside_flag
        j = i
    return inside_flag


def _lies_on_segment(
    px: float,
    py: float,
    qx: float,
    qy: float,
    rx: float,
    ry: float,
) -> bool:
    """Return True if point Q lies on segment PR.

    Args:
        px: X coordinate of point P.
        py: Y coordinate of point P.
        qx: X coordinate of point Q (candidate).
        qy: Y coordinate of point Q (candidate).
        rx: X coordinate of point R.
        ry: Y coordinate of point R.
    """
    return (qx <= max(px, rx)) and (qx >= min(px, rx)) and (qy <= max(py, ry)) and (qy >= min(py, ry))


def _orientation(
    px: float,
    py: float,
    qx: float,
    qy: float,
    rx: float,
    ry: float,
) -> int:
    """Return the orientation of the ordered triple (P, Q, R).

    Args:
        px: X coordinate of P.
        py: Y coordinate of P.
        qx: X coordinate of Q.
        qy: Y coordinate of Q.
        rx: X coordinate of R.
        ry: Y coordinate of R.

    Returns:
        0 if collinear, 1 if clockwise, 2 if counterclockwise.
    """
    val = (qy - py) * (rx - qx) - (qx - px) * (ry - qy)
    if val > 0:
        return 1
    if val < 0:
        return 2
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
    """Return True if segment PQ intersects segment RS.

    Args:
        px: X coordinate of P (start of first segment).
        py: Y coordinate of P.
        qx: X coordinate of Q (end of first segment).
        qy: Y coordinate of Q.
        rx: X coordinate of R (start of second segment).
        ry: Y coordinate of R.
        sx: X coordinate of S (end of second segment).
        sy: Y coordinate of S.

    Returns:
        True if the two segments intersect (including touching endpoints).
    """
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
    return bool(o4 == 0 and _lies_on_segment(rx, ry, qx, qy, sx, sy))


def polygon_edges(
    polygon: list[dict],
) -> Generator[tuple[dict, dict], None, None]:
    """Yield consecutive edge pairs (p1, p2) for the given polygon.

    Args:
        polygon: Ordered list of {'lat': ..., 'lon': ...} vertex dicts.

    Yields:
        Pairs of adjacent vertex dicts representing each polygon edge,
        wrapping from the last vertex back to the first.
    """
    n = len(polygon)
    for i in range(n):
        yield polygon[i], polygon[(i + 1) % n]
