"""Strict single-polygon KML parsing shared by the v1 and v2 geofence readers."""

from __future__ import annotations

import math
from typing import Any

KML_NS = "{http://www.opengis.net/kml/2.2}"


def polygon_from_kml(root: Any, file_path: str) -> list[dict]:
    """Extract the single outer ring of a parsed KML tree.

    Raises:
        ValueError: If the KML has no polygon, more than one, holes, or a
            malformed or non-finite coordinate.
    """

    def find(tag: str) -> list:
        return root.findall(f".//{KML_NS}{tag}") or root.findall(f".//{tag}")

    polygons = find("Polygon")
    if len(polygons) != 1:
        raise ValueError(f"Geofence KML must contain exactly one Polygon, found {len(polygons)}: {file_path}")
    if find("innerBoundaryIs"):
        raise ValueError(f"Geofence KML polygons with holes are not supported: {file_path}")
    rings = find("coordinates")
    if len(rings) != 1 or not (rings[0].text or "").strip():
        raise ValueError(f"Geofence KML must have one outer ring with coordinates: {file_path}")

    polygon = []
    for str_val in rings[0].text.split():
        parts = str_val.split(",")
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except (IndexError, ValueError) as e:
            raise ValueError(f"Malformed geofence coordinate {str_val!r} in {file_path}") from e
        if not (math.isfinite(lon) and math.isfinite(lat)):
            raise ValueError(f"Non-finite geofence coordinate {str_val!r} in {file_path}")
        polygon.append({"lon": lon, "lat": lat})
    if len(polygon) < 3:
        raise ValueError(f"Geofence polygon needs at least 3 points: {file_path}")
    return polygon
