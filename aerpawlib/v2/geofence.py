"""
Geofence utilities for aerpawlib v2.

Extracted from v1 util.
"""

from __future__ import annotations

from typing import Generator, List, Tuple


def read_geofence(file_path: str) -> List[dict]:
    """
    Parse a KML file into a list of lat/lon points.

    Handles KML files with any nesting depth (Folder, multiple Placemarks, etc.).
    Uses the first Polygon with an outerBoundaryIs/LinearRing found in the document.

    Returns:
        List of {'lat': ..., 'lon': ...} dicts.

    Raises:
        ValueError: If no Polygon with a LinearRing is found in the KML.
    """
    from pykml import parser
    from lxml import etree

    with open(file_path, "rb") as f:
        root = parser.fromstring(f.read())

    # Search the entire element tree for the first LinearRing coordinates
    nsmap = {"kml": "http://www.opengis.net/kml/2.2"}
    coords_el = None

    # Try with the standard KML namespace first
    for xpath in [
        ".//{http://www.opengis.net/kml/2.2}outerBoundaryIs/"
        "{http://www.opengis.net/kml/2.2}LinearRing/"
        "{http://www.opengis.net/kml/2.2}coordinates",
        ".//outerBoundaryIs/LinearRing/coordinates",
    ]:
        results = root.findall(xpath)
        if results:
            coords_el = results[0]
            break

    if coords_el is None or not coords_el.text:
        raise ValueError(
            f"No Polygon/outerBoundaryIs/LinearRing/coordinates found in KML: {file_path}"
        )

    coords_str = coords_el.text.strip()
    polygon = []
    for s in coords_str.split():
        parts = s.split(",")
        polygon.append({"lon": float(parts[0]), "lat": float(parts[1])})
    return polygon


def inside(lon: float, lat: float, geofence: List[dict]) -> bool:
    """Check if point (lon, lat) is inside polygon using ray-casting.

    Handles degenerate (horizontal) edges safely by skipping division-by-zero cases.
    """
    n = len(geofence)
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
