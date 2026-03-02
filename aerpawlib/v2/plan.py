"""
QGroundControl .plan file parsing for aerpawlib v2.
"""

from __future__ import annotations

import json
from typing import List, Tuple

from .constants import (
    DEFAULT_WAYPOINT_SPEED,
    PLAN_CMD_TAKEOFF,
    PLAN_CMD_WAYPOINT,
    PLAN_CMD_RTL,
    PLAN_CMD_SPEED,
)
from .types import Coordinate

# Waypoint tuple: (command, x/lat, y/lon, z/alt, waypoint_id, speed)
Waypoint = Tuple[int, float, float, float, int, float]


def read_from_plan(
    path: str, default_speed: float = DEFAULT_WAYPOINT_SPEED
) -> List[Waypoint]:
    """
    Parse a QGroundControl .plan file into a list of waypoints.

    Args:
        path: Path to the .plan file.
        default_speed: Speed (m/s) to use if none specified in plan.

    Returns:
        List of waypoint tuples (command, x, y, z, waypoint_id, speed).

    Raises:
        Exception: If the file is not a valid .plan file.
    """
    waypoints: List[Waypoint] = []
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
    Extract a Coordinate from a waypoint tuple.

    Args:
        waypoint: The waypoint tuple (command, x, y, z, waypoint_id, speed).

    Returns:
        Coordinate with lat=x, lon=y, alt=z.
    """
    return Coordinate(waypoint[1], waypoint[2], waypoint[3])


def read_from_plan_complete(
    path: str, default_speed: float = DEFAULT_WAYPOINT_SPEED
) -> List[dict]:
    """
    Read a .plan file and return detailed waypoint dictionaries.

    Includes id, command, pos, wait_for, speed.

    Args:
        path: Path to the .plan file.
        default_speed: Default speed in m/s.

    Returns:
        List of waypoint dicts with id, command, pos, wait_for, speed.
    """
    waypoints: List[dict] = []
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
