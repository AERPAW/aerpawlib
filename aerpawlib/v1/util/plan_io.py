"""
QGroundControl plan file parsing helpers for v1.

This module reads `.plan` JSON mission files and converts mission items into
v1 waypoint structures used by runner and vehicle logic.

Capabilities
- Parse core mission commands (takeoff, waypoint, speed, RTL).
- Produce tuple-based or detailed dictionary waypoint representations.
- Convert waypoint entries into `Coordinate` objects.

Usage:
- Use these helpers when loading pre-authored missions from QGC into v1
  scripts.
"""

import json
from typing import Dict, List

from ..constants import (
    DEFAULT_WAYPOINT_SPEED,
    PLAN_CMD_RTL,
    PLAN_CMD_SPEED,
    PLAN_CMD_TAKEOFF,
    PLAN_CMD_WAYPOINT,
)
from .geometry import Coordinate, Waypoint


def read_from_plan(
    path: str, default_speed: float = DEFAULT_WAYPOINT_SPEED
) -> List[Waypoint]:
    """
    Parse a QGroundControl .plan file into a list of Waypoints.

    Args:
        path: Path to the .plan file.
        default_speed: Speed to use if none specified in plan.
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
            if len(item.get("params", [])) < 7:
                raise ValueError(f"Plan item has fewer than 7 params: {item}")
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
        waypoint: The waypoint tuple.

    Returns:
        Coordinate: The extracted location.
    """
    return Coordinate(waypoint[1], waypoint[2], waypoint[3])


def read_from_plan_complete(
    path: str, default_speed: float = DEFAULT_WAYPOINT_SPEED
) -> List[Dict]:
    """
    Read a .plan file and return detailed waypoint dictionaries.

    Includes additional fields like wait_for delay.

    Args:
        path: Path to the .plan file.
        default_speed: Default speed in m/s.

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
            if len(item.get("params", [])) < 7:
                raise ValueError(f"Plan item has fewer than 7 params: {item}")
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
