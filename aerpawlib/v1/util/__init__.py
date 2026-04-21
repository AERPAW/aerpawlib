"""
Utility re-exports for the v1 API.

This package gathers shared geometry, plan parsing, geofence, and port helper
symbols into a stable import surface used throughout v1 code.

Capabilities
- Re-export coordinate and vector primitives.
- Re-export plan, geofence, and intersection helpers.
- Re-export TCP/UDP local port availability checks.

Usage:
- Import from `aerpawlib.v1.util` to keep mission and library code aligned with
  the canonical v1 utility namespace.
"""

from .geometry import Coordinate, VectorNED, Waypoint
from .geofence import (
    doIntersect,
    do_intersect,
    inside,
    liesOnSegment,
    lies_on_segment,
    orientation,
    readGeofence,
    read_geofence,
)
from .plan_io import (
    get_location_from_waypoint,
    read_from_plan,
    read_from_plan_complete,
)
from .ports import is_tcp_port_in_use, is_udp_port_in_use

__all__ = [
    "Coordinate",
    "VectorNED",
    "Waypoint",
    "read_from_plan",
    "get_location_from_waypoint",
    "read_from_plan_complete",
    "read_geofence",
    "readGeofence",
    "inside",
    "lies_on_segment",
    "liesOnSegment",
    "orientation",
    "do_intersect",
    "doIntersect",
    "is_udp_port_in_use",
    "is_tcp_port_in_use",
]
