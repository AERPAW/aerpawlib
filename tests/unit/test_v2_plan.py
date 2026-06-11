"""Unit tests for aerpawlib v2 plan module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from aerpawlib.v2.constants import (
    DEFAULT_WAYPOINT_SPEED,
    PLAN_CMD_RTL,
    PLAN_CMD_SPEED,
    PLAN_CMD_TAKEOFF,
    PLAN_CMD_WAYPOINT,
)
from aerpawlib.v2.exceptions import PlanError
from aerpawlib.v2.plan import (
    get_location_from_waypoint,
    read_from_plan,
    read_from_plan_complete,
)
from aerpawlib.v2.types import Coordinate


@pytest.fixture
def sample_plan_path() -> str:
    data = {
        "fileType": "Plan",
        "mission": {
            "items": [
                {
                    "command": PLAN_CMD_TAKEOFF,
                    "params": [0, 0, 0, 0, 35.7274, -78.6960, 10],
                    "doJumpId": 1,
                },
                {
                    "command": PLAN_CMD_WAYPOINT,
                    "params": [0, 0, 0, 0, 35.7284, -78.6960, 20],
                    "doJumpId": 2,
                },
                {
                    "command": PLAN_CMD_RTL,
                    "params": [0, 0, 0, 0, 0, 0, 0],
                    "doJumpId": 3,
                },
            ],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".plan", delete=False) as f:
        json.dump(data, f)
        path = f.name
    yield path
    Path(path).unlink()


def test_read_from_plan(sample_plan_path: str):
    wps = read_from_plan(Path(sample_plan_path))
    assert len(wps) == 3
    assert wps[0][0] == PLAN_CMD_TAKEOFF
    assert wps[0][1] == 35.7274 and wps[0][3] == 10


def test_read_from_plan_wrong_type():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"fileType": "NotAPlan", "mission": {"items": []}}, f)
        path = f.name
    try:
        with pytest.raises(PlanError, match="Wrong file type"):
            read_from_plan(Path(path))
    finally:
        Path(path).unlink()


def test_get_location_from_waypoint(sample_plan_path: str):
    wps = read_from_plan(Path(sample_plan_path))
    c = get_location_from_waypoint(wps[0])
    assert isinstance(c, Coordinate)
    assert c.lat == 35.7274 and c.alt == 10


def test_read_from_plan_complete(sample_plan_path: str):
    wps = read_from_plan_complete(Path(sample_plan_path))
    assert len(wps) == 3
    assert "id" in wps[0] and "pos" in wps[0] and "wait_for" in wps[0]


def test_speed_change_applied_to_following_waypoints():
    data = {
        "fileType": "Plan",
        "mission": {
            "items": [
                {
                    "command": PLAN_CMD_TAKEOFF,
                    "params": [0, 0, 0, 0, 35.72, -78.69, 10],
                    "doJumpId": 1,
                },
                {
                    "command": PLAN_CMD_SPEED,
                    "params": [0, 12.0, 0, 0, 0, 0, 0],
                    "doJumpId": 2,
                },
                {
                    "command": PLAN_CMD_WAYPOINT,
                    "params": [0, 0, 0, 0, 35.73, -78.69, 20],
                    "doJumpId": 3,
                },
                {
                    "command": PLAN_CMD_RTL,
                    "params": [0, 0, 0, 0, 0, 0, 0],
                    "doJumpId": 4,
                },
            ],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".plan", delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        wps = read_from_plan(Path(path))
        assert len(wps) == 3
        assert wps[0][5] == DEFAULT_WAYPOINT_SPEED
        assert wps[1][5] == 12.0
        assert wps[2][5] == 12.0
    finally:
        Path(path).unlink()


def test_read_from_plan_empty_mission():
    data = {"fileType": "Plan", "mission": {"items": []}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".plan", delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        wps = read_from_plan(Path(path))
        assert wps == []
    finally:
        Path(path).unlink()
