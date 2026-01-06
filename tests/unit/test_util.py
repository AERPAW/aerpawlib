"""
Unit tests for utility functions.

Tests geofence, waypoint reading, plan file parsing, etc.
"""
import pytest
import json
import tempfile
import os
from aerpawlib.v1.util import (
    Coordinate,
    read_from_plan,
    read_from_plan_complete,
    get_location_from_waypoint,
    inside,
    doIntersect,
    orientation,
    liesOnSegment,
    _PLAN_CMD_TAKEOFF,
    _PLAN_CMD_WAYPOINT,
    _PLAN_CMD_RTL,
)


class TestPlanFileReading:
    """Tests for .plan file reading."""

    @pytest.fixture
    def sample_plan_file(self):
        """Create a sample .plan file for testing."""
        plan_data = {
            "fileType": "Plan",
            "mission": {
                "items": [
                    {
                        "command": _PLAN_CMD_TAKEOFF,
                        "params": [0, 0, 0, 0, 35.7274, -78.6960, 10],
                        "doJumpId": 1
                    },
                    {
                        "command": _PLAN_CMD_WAYPOINT,
                        "params": [0, 0, 0, 0, 35.7284, -78.6960, 20],
                        "doJumpId": 2
                    },
                    {
                        "command": _PLAN_CMD_WAYPOINT,
                        "params": [0, 0, 0, 0, 35.7284, -78.6950, 20],
                        "doJumpId": 3
                    },
                    {
                        "command": _PLAN_CMD_RTL,
                        "params": [0, 0, 0, 0, 0, 0, 0],
                        "doJumpId": 4
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.plan', delete=False) as f:
            json.dump(plan_data, f)
            temp_path = f.name

        yield temp_path
        os.unlink(temp_path)

    def test_read_from_plan(self, sample_plan_file):
        """Test reading waypoints from plan file."""
        waypoints = read_from_plan(sample_plan_file)

        assert len(waypoints) == 4  # takeoff, 2 waypoints, rtl

        # Check first waypoint (takeoff)
        assert waypoints[0][0] == _PLAN_CMD_TAKEOFF
        assert waypoints[0][1] == 35.7274  # lat
        assert waypoints[0][2] == -78.6960  # lon
        assert waypoints[0][3] == 10  # alt

    def test_read_from_plan_default_speed(self, sample_plan_file):
        """Test waypoints have default speed when not specified."""
        waypoints = read_from_plan(sample_plan_file, default_speed=10.0)

        for wp in waypoints:
            assert wp[5] == 10.0  # speed

    def test_read_from_plan_wrong_file_type(self):
        """Test reading non-plan file raises exception."""
        bad_data = {"fileType": "NotAPlan", "mission": {"items": []}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(bad_data, f)
            temp_path = f.name

        try:
            with pytest.raises(Exception, match="Wrong file type"):
                read_from_plan(temp_path)
        finally:
            os.unlink(temp_path)

    def test_get_location_from_waypoint(self, sample_plan_file):
        """Test extracting Coordinate from waypoint."""
        waypoints = read_from_plan(sample_plan_file)
        coord = get_location_from_waypoint(waypoints[0])

        assert isinstance(coord, Coordinate)
        assert coord.lat == 35.7274
        assert coord.lon == -78.6960
        assert coord.alt == 10


class TestPlanFileWithSpeed:
    """Tests for plan files with speed commands."""

    @pytest.fixture
    def plan_with_speed(self):
        """Create a plan file with speed commands."""
        plan_data = {
            "fileType": "Plan",
            "mission": {
                "items": [
                    {
                        "command": _PLAN_CMD_TAKEOFF,
                        "params": [0, 0, 0, 0, 35.7274, -78.6960, 10],
                        "doJumpId": 1
                    },
                    {
                        "command": 178,  # Speed command
                        "params": [0, 5.0, 0, 0, 0, 0, 0],  # 5 m/s
                        "doJumpId": 2
                    },
                    {
                        "command": _PLAN_CMD_WAYPOINT,
                        "params": [0, 0, 0, 0, 35.7284, -78.6960, 20],
                        "doJumpId": 3
                    },
                    {
                        "command": 178,  # Speed command
                        "params": [0, 10.0, 0, 0, 0, 0, 0],  # 10 m/s
                        "doJumpId": 4
                    },
                    {
                        "command": _PLAN_CMD_WAYPOINT,
                        "params": [0, 0, 0, 0, 35.7294, -78.6960, 20],
                        "doJumpId": 5
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.plan', delete=False) as f:
            json.dump(plan_data, f)
            temp_path = f.name

        yield temp_path
        os.unlink(temp_path)

    def test_speed_command_updates_following_waypoints(self, plan_with_speed):
        """Test speed command affects following waypoints."""
        waypoints = read_from_plan(plan_with_speed, default_speed=3.0)

        # First waypoint should have default speed
        assert waypoints[0][5] == 3.0

        # Second waypoint should have 5 m/s (after first speed command)
        assert waypoints[1][5] == 5.0

        # Third waypoint should have 10 m/s (after second speed command)
        assert waypoints[2][5] == 10.0


class TestReadFromPlanComplete:
    """Tests for read_from_plan_complete function."""

    @pytest.fixture
    def plan_with_delays(self):
        """Create a plan file with delay values."""
        plan_data = {
            "fileType": "Plan",
            "mission": {
                "items": [
                    {
                        "command": _PLAN_CMD_WAYPOINT,
                        "params": [5.0, 0, 0, 0, 35.7274, -78.6960, 10],  # 5s delay
                        "doJumpId": 1
                    },
                    {
                        "command": _PLAN_CMD_WAYPOINT,
                        "params": [0, 0, 0, 0, 35.7284, -78.6960, 20],  # no delay
                        "doJumpId": 2
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.plan', delete=False) as f:
            json.dump(plan_data, f)
            temp_path = f.name

        yield temp_path
        os.unlink(temp_path)

    def test_read_complete_returns_dicts(self, plan_with_delays):
        """Test read_from_plan_complete returns dictionaries."""
        waypoints = read_from_plan_complete(plan_with_delays)

        assert len(waypoints) == 2
        assert isinstance(waypoints[0], dict)

    def test_read_complete_includes_delay(self, plan_with_delays):
        """Test read_from_plan_complete includes wait_for field."""
        waypoints = read_from_plan_complete(plan_with_delays)

        assert waypoints[0]["wait_for"] == 5.0
        assert waypoints[1]["wait_for"] == 0

    def test_read_complete_includes_all_fields(self, plan_with_delays):
        """Test read_from_plan_complete includes all expected fields."""
        waypoints = read_from_plan_complete(plan_with_delays)

        wp = waypoints[0]
        assert "id" in wp
        assert "command" in wp
        assert "pos" in wp
        assert "wait_for" in wp
        assert "speed" in wp


class TestGeofence:
    """Tests for geofence functions."""

    @pytest.fixture
    def square_geofence(self):
        """Create a simple square geofence."""
        return [
            {"lon": -78.70, "lat": 35.72},
            {"lon": -78.70, "lat": 35.74},
            {"lon": -78.68, "lat": 35.74},
            {"lon": -78.68, "lat": 35.72},
            {"lon": -78.70, "lat": 35.72},  # Close the polygon
        ]

    def test_inside_point_in_square(self, square_geofence):
        """Test point inside square geofence."""
        # Center of the square
        lon, lat = -78.69, 35.73
        assert inside(lon, lat, square_geofence) is True

    def test_inside_point_outside_square(self, square_geofence):
        """Test point outside square geofence."""
        # Way outside
        lon, lat = -78.50, 35.73
        assert inside(lon, lat, square_geofence) is False

    def test_inside_point_on_edge(self, square_geofence):
        """Test point on edge of geofence."""
        # On the western edge
        lon, lat = -78.70, 35.73
        # Edge behavior can vary, just ensure it returns a boolean
        result = inside(lon, lat, square_geofence)
        assert isinstance(result, bool)

    def test_inside_point_at_corner(self, square_geofence):
        """Test point at corner of geofence."""
        lon, lat = -78.70, 35.72
        result = inside(lon, lat, square_geofence)
        assert isinstance(result, bool)


class TestLineIntersection:
    """Tests for line intersection functions."""

    def test_do_intersect_crossing_lines(self):
        """Test two crossing lines intersect."""
        # Line 1: (0,0) to (10,10)
        # Line 2: (0,10) to (10,0)
        result = doIntersect(0, 0, 10, 10, 0, 10, 10, 0)
        assert result is True

    def test_do_intersect_parallel_lines(self):
        """Test parallel lines don't intersect."""
        # Line 1: (0,0) to (10,0)
        # Line 2: (0,1) to (10,1)
        result = doIntersect(0, 0, 10, 0, 0, 1, 10, 1)
        assert result is False

    def test_do_intersect_non_crossing_lines(self):
        """Test non-crossing lines don't intersect."""
        # Line 1: (0,0) to (5,5)
        # Line 2: (10,0) to (10,10)
        result = doIntersect(0, 0, 5, 5, 10, 0, 10, 10)
        assert result is False

    def test_orientation_clockwise(self):
        """Test clockwise orientation detection."""
        # Points arranged clockwise
        result = orientation(0, 0, 1, 1, 1, 0)
        assert result == 1  # Clockwise

    def test_orientation_counterclockwise(self):
        """Test counterclockwise orientation detection."""
        # Points arranged counterclockwise
        result = orientation(0, 0, 1, 0, 1, 1)
        assert result == 2  # Counterclockwise

    def test_orientation_colinear(self):
        """Test colinear points detection."""
        # Three points on a line
        result = orientation(0, 0, 1, 1, 2, 2)
        assert result == 0  # Colinear

    def test_lies_on_segment_true(self):
        """Test point lies on segment."""
        # Point (1,1) is on segment from (0,0) to (2,2)
        result = liesOnSegment(0, 0, 1, 1, 2, 2)
        assert result is True

    def test_lies_on_segment_false(self):
        """Test point doesn't lie on segment."""
        # Point (3,3) is outside segment from (0,0) to (2,2)
        result = liesOnSegment(0, 0, 3, 3, 2, 2)
        assert result is False

