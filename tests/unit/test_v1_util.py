"""Unit tests for aerpawlib v1 util module (Coordinate, VectorNED, plan, geofence)."""

import json
import os
import tempfile

import pytest

from aerpawlib.v1.constants import PLAN_CMD_RTL, PLAN_CMD_TAKEOFF, PLAN_CMD_WAYPOINT
from aerpawlib.v1.util import (
    Coordinate,
    VectorNED,
    doIntersect,
    get_location_from_waypoint,
    inside,
    liesOnSegment,
    orientation,
    read_from_plan,
    read_from_plan_complete,
    read_geofence,
)


class TestVectorNED:
    """VectorNED creation and operations."""

    def test_create(self):
        v = VectorNED(1.0, 2.0, 3.0)
        assert v.north == 1.0 and v.east == 2.0 and v.down == 3.0

    def test_default_down(self):
        v = VectorNED(1.0, 2.0)
        assert v.down == 0

    def test_add(self):
        v1, v2 = VectorNED(1, 2, 3), VectorNED(4, 5, 6)
        r = v1 + v2
        assert r.north == 5 and r.east == 7 and r.down == 9

    def test_subtract(self):
        v1, v2 = VectorNED(5, 7, 9), VectorNED(1, 2, 3)
        r = v1 - v2
        assert r.north == 4 and r.east == 5 and r.down == 6

    def test_multiply_scalar(self):
        v = VectorNED(2, 3, 4)
        assert (v * 2).north == 4 and (v * 2).east == 6

    def test_rmul(self):
        v = VectorNED(2, 3, 4)
        assert (3 * v).north == 6

    def test_hypot(self):
        assert VectorNED(3, 4, 0).hypot() == 5.0
        assert VectorNED(0, 0, 0).hypot() == 0

    def test_hypot_ignore_down(self):
        assert VectorNED(3, 4, 100).hypot(ignore_down=True) == 5.0

    def test_norm(self):
        v = VectorNED(3, 4, 0)
        n = v.norm()
        assert abs(n.hypot() - 1.0) < 1e-10

    def test_norm_zero(self):
        assert VectorNED(0, 0, 0).norm().hypot() == 0

    def test_rotate_by_angle(self):
        v = VectorNED(1, 0, 0)
        r = v.rotate_by_angle(90)
        assert abs(r.north) < 1e-10 and abs(r.east - (-1)) < 1e-10

    def test_cross_product(self):
        n, e = VectorNED(1, 0, 0), VectorNED(0, 1, 0)
        c = n.cross_product(e)
        assert abs(c.down - 1) < 1e-10

    def test_add_invalid_raises(self):
        with pytest.raises(TypeError):
            VectorNED(1, 2, 3) + 5

    def test_subtract_invalid_raises(self):
        with pytest.raises(TypeError):
            VectorNED(1, 2, 3) - 5


class TestCoordinate:
    """Coordinate creation and operations."""

    def test_create(self):
        c = Coordinate(35.7274, -78.6960, 100.0)
        assert c.lat == 35.7274 and c.lon == -78.6960 and c.alt == 100.0

    def test_default_alt(self):
        c = Coordinate(35.7274, -78.6960)
        assert c.alt == 0

    def test_distance_same(self):
        c = Coordinate(35.7274, -78.6960, 100)
        assert c.distance(c) == 0

    def test_ground_distance_ignores_alt(self):
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6960, 100)
        assert c1.ground_distance(c2) < 1

    def test_bearing_north(self):
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7374, -78.6960, 0)
        b = c1.bearing(c2)
        assert abs(b) < 1 or abs(b - 360) < 1

    def test_add_vector(self):
        c = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(100, 0, 0)
        r = c + v
        assert r.lat > c.lat and abs(r.lon - c.lon) < 1e-6

    def test_subtract_coordinates_gives_vector(self):
        c1 = Coordinate(35.7274, -78.6960, 100)
        c2 = Coordinate(35.7274, -78.6960, 0)
        r = c1 - c2
        assert isinstance(r, VectorNED)

    def test_to_json(self):
        c = Coordinate(35.7274, -78.6960, 100)
        j = json.loads(c.toJson())
        assert j["lat"] == 35.7274 and j["lon"] == -78.6960


class TestPlanFile:
    """Plan file reading."""

    @pytest.fixture
    def sample_plan(self):
        data = {
            "fileType": "Plan",
            "mission": {
                "items": [
                    {"command": PLAN_CMD_TAKEOFF, "params": [0, 0, 0, 0, 35.7274, -78.6960, 10], "doJumpId": 1},
                    {"command": PLAN_CMD_WAYPOINT, "params": [0, 0, 0, 0, 35.7284, -78.6960, 20], "doJumpId": 2},
                    {"command": PLAN_CMD_RTL, "params": [0, 0, 0, 0, 0, 0, 0], "doJumpId": 3},
                ]
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".plan", delete=False) as f:
            json.dump(data, f)
            path = f.name
        yield path
        os.unlink(path)

    def test_read_from_plan(self, sample_plan):
        wps = read_from_plan(sample_plan)
        assert len(wps) == 3
        assert wps[0][0] == PLAN_CMD_TAKEOFF
        assert wps[0][1] == 35.7274 and wps[0][3] == 10

    def test_read_from_plan_wrong_type(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"fileType": "NotAPlan", "mission": {"items": []}}, f)
            path = f.name
        try:
            with pytest.raises(Exception, match="Wrong file type"):
                read_from_plan(path)
        finally:
            os.unlink(path)

    def test_get_location_from_waypoint(self, sample_plan):
        wps = read_from_plan(sample_plan)
        c = get_location_from_waypoint(wps[0])
        assert isinstance(c, Coordinate)
        assert c.lat == 35.7274 and c.alt == 10

    def test_read_from_plan_complete(self, sample_plan):
        wps = read_from_plan_complete(sample_plan)
        assert len(wps) == 3
        assert "id" in wps[0] and "pos" in wps[0] and "wait_for" in wps[0]


class TestGeofence:
    """Geofence and geometry functions."""

    @pytest.fixture
    def square_geofence(self):
        return [
            {"lon": -78.70, "lat": 35.72},
            {"lon": -78.70, "lat": 35.74},
            {"lon": -78.68, "lat": 35.74},
            {"lon": -78.68, "lat": 35.72},
            {"lon": -78.70, "lat": 35.72},
        ]

    def test_inside_true(self, square_geofence):
        assert inside(-78.69, 35.73, square_geofence) is True

    def test_inside_false(self, square_geofence):
        assert inside(-78.50, 35.73, square_geofence) is False

    def test_orientation_colinear(self):
        assert orientation(0, 0, 1, 1, 2, 2) == 0

    def test_orientation_clockwise(self):
        assert orientation(0, 0, 1, 1, 1, 0) == 1

    def test_do_intersect_crossing(self):
        assert doIntersect(0, 0, 10, 10, 0, 10, 10, 0) is True

    def test_do_intersect_parallel(self):
        assert doIntersect(0, 0, 10, 0, 0, 1, 10, 1) is False

    def test_lies_on_segment_true(self):
        assert liesOnSegment(0, 0, 1, 1, 2, 2) is True

    def test_lies_on_segment_false(self):
        assert liesOnSegment(0, 0, 3, 3, 2, 2) is False


class TestReadGeofence:
    """read_geofence from KML."""

    @pytest.fixture
    def minimal_kml(self):
        kml = """<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<Placemark>
<Polygon>
<outerBoundaryIs>
<LinearRing>
<coordinates>-78.70,35.72,0 -78.70,35.74,0 -78.68,35.74,0 -78.68,35.72,0 -78.70,35.72,0</coordinates>
</LinearRing>
</outerBoundaryIs>
</Polygon>
</Placemark>
</Document>
</kml>"""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".kml", delete=False) as f:
            f.write(kml.encode())
            path = f.name
        yield path
        os.unlink(path)

    def test_read_geofence_returns_polygon(self, minimal_kml):
        poly = read_geofence(minimal_kml)
        assert len(poly) >= 4
        assert all("lat" in p and "lon" in p for p in poly)
