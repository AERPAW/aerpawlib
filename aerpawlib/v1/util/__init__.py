"""
Types and functions commonly used throughout the aerpawlib v1 framework.

This version has been updated to remove DroneKit dependencies while
maintaining API compatibility.

@author: Julian Reder (quantumbagel)
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
