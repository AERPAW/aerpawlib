"""
Unit tests for Coordinate class.

Tests coordinate operations including distance, bearing, arithmetic with vectors, etc.
"""
import pytest
from aerpawlib.v1.util import Coordinate, VectorNED


class TestCoordinateCreation:
    """Tests for Coordinate initialization."""

    def test_create_with_all_components(self):
        """Test creating a coordinate with lat, lon, alt."""
        c = Coordinate(35.7274, -78.6960, 100.0)
        assert c.lat == 35.7274
        assert c.lon == -78.6960
        assert c.alt == 100.0

    def test_create_with_default_alt(self):
        """Test creating a coordinate with default alt=0."""
        c = Coordinate(35.7274, -78.6960)
        assert c.lat == 35.7274
        assert c.lon == -78.6960
        assert c.alt == 0

    def test_create_at_origin(self):
        """Test creating a coordinate at (0, 0)."""
        c = Coordinate(0, 0, 0)
        assert c.lat == 0
        assert c.lon == 0
        assert c.alt == 0

    def test_create_negative_coordinates(self):
        """Test creating a coordinate with negative lat/lon."""
        c = Coordinate(-33.8688, 151.2093, 50)  # Sydney
        assert c.lat == -33.8688
        assert c.lon == 151.2093


class TestCoordinateDistance:
    """Tests for Coordinate distance calculations."""

    def test_distance_same_point(self):
        """Test distance between same point is zero."""
        c = Coordinate(35.7274, -78.6960, 100)
        assert c.distance(c) == 0

    def test_distance_nearby_points(self):
        """Test distance calculation for nearby points."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7284, -78.6960, 0)  # ~111m north
        distance = c1.distance(c2)
        assert 100 < distance < 120  # Approximately 111m

    def test_distance_includes_altitude(self):
        """Test that distance includes altitude difference."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6960, 100)
        distance = c1.distance(c2)
        assert abs(distance - 100) < 1  # Should be ~100m

    def test_ground_distance_ignores_altitude(self):
        """Test ground_distance ignores altitude."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6960, 100)
        ground_dist = c1.ground_distance(c2)
        assert ground_dist < 1  # Should be ~0

    def test_ground_distance_same_point(self):
        """Test ground_distance between same point is zero."""
        c = Coordinate(35.7274, -78.6960, 100)
        assert c.ground_distance(c) == 0

    def test_distance_invalid_type_raises(self):
        """Test distance with non-Coordinate raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c.distance((35.7284, -78.6960, 0))

    def test_ground_distance_invalid_type_raises(self):
        """Test ground_distance with non-Coordinate raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c.ground_distance("invalid")

    def test_distance_is_symmetric(self):
        """Test distance(a, b) == distance(b, a)."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7384, -78.6860, 50)
        assert abs(c1.distance(c2) - c2.distance(c1)) < 0.001


class TestCoordinateBearing:
    """Tests for Coordinate bearing calculations."""

    def test_bearing_north(self):
        """Test bearing to point directly north is ~0°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7374, -78.6960, 0)  # North
        bearing = c1.bearing(c2)
        assert abs(bearing) < 1 or abs(bearing - 360) < 1

    def test_bearing_east(self):
        """Test bearing to point directly east is ~90°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6860, 0)  # East
        bearing = c1.bearing(c2)
        assert abs(bearing - 90) < 1

    def test_bearing_south(self):
        """Test bearing to point directly south is ~180°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7174, -78.6960, 0)  # South
        bearing = c1.bearing(c2)
        assert abs(bearing - 180) < 1

    def test_bearing_west(self):
        """Test bearing to point directly west is ~270°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.7060, 0)  # West
        bearing = c1.bearing(c2)
        assert abs(bearing - 270) < 1

    def test_bearing_wraps_360(self):
        """Test bearing is wrapped to 0-360 range."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7374, -78.6960, 0)
        bearing = c1.bearing(c2, wrap_360=True)
        assert 0 <= bearing < 360

    def test_bearing_no_wrap(self):
        """Test bearing without wrapping can be negative."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7374, -78.7060, 0)  # NW
        bearing = c1.bearing(c2, wrap_360=False)
        # Just verify it returns a value (could be negative)
        assert isinstance(bearing, float)

    def test_bearing_invalid_type_raises(self):
        """Test bearing with non-Coordinate raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c.bearing((35.7374, -78.6960, 0))


class TestCoordinateArithmetic:
    """Tests for Coordinate arithmetic with VectorNED."""

    def test_add_vector_north(self):
        """Test adding a northward vector moves coordinate north."""
        c = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(100, 0, 0)  # 100m north
        result = c + v
        assert result.lat > c.lat
        assert abs(result.lon - c.lon) < 1e-6
        assert result.alt == c.alt

    def test_add_vector_east(self):
        """Test adding an eastward vector moves coordinate east."""
        c = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(0, 100, 0)  # 100m east
        result = c + v
        assert abs(result.lat - c.lat) < 1e-6
        assert result.lon > c.lon
        assert result.alt == c.alt

    def test_add_vector_down_decreases_alt(self):
        """Test adding a downward vector decreases altitude."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(0, 0, 50)  # 50m down
        result = c + v
        assert result.alt == 50  # 100 - 50 = 50

    def test_add_vector_up_increases_alt(self):
        """Test adding an upward vector increases altitude."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(0, 0, -50)  # 50m up (negative down)
        result = c + v
        assert result.alt == 150  # 100 + 50 = 150

    def test_add_zero_vector(self):
        """Test adding zero vector returns same coordinate."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(0, 0, 0)
        result = c + v
        assert result.lat == c.lat
        assert result.lon == c.lon
        assert result.alt == c.alt

    def test_add_invalid_type_raises(self):
        """Test adding non-VectorNED raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c + (100, 50, 0)
        with pytest.raises(TypeError):
            c + 100

    def test_subtract_vector(self):
        """Test subtracting a vector."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(100, 50, 0)
        result = c - v
        # Subtracting north should move south
        assert result.lat < c.lat

    def test_subtract_coordinates_gives_vector(self):
        """Test subtracting coordinates gives a VectorNED."""
        c1 = Coordinate(35.7274, -78.6960, 100)
        c2 = Coordinate(35.7274, -78.6960, 0)
        result = c1 - c2
        assert isinstance(result, VectorNED)
        # Same lat/lon, different alt
        assert abs(result.north) < 1
        assert abs(result.east) < 1
        assert abs(result.down - (-100)) < 1  # c1 is 100m higher

    def test_add_then_subtract_roundtrip(self):
        """Test adding then subtracting a vector returns near original."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(500, 300, -50)
        result = (c + v) - v
        assert abs(result.lat - c.lat) < 1e-6
        assert abs(result.lon - c.lon) < 1e-6
        assert abs(result.alt - c.alt) < 0.01


class TestCoordinateStr:
    """Tests for Coordinate string representation."""

    def test_str_format(self):
        """Test string format contains lat, lon, alt."""
        c = Coordinate(35.7274, -78.6960, 100.5)
        s = str(c)
        assert "35.7274" in s
        assert "-78.6960" in s or "78.696" in s
        assert "100.5" in s


class TestCoordinateJson:
    """Tests for Coordinate JSON serialization."""

    def test_to_json(self):
        """Test toJson returns valid JSON string."""
        import json
        c = Coordinate(35.7274, -78.6960, 100)
        json_str = c.toJson()
        parsed = json.loads(json_str)
        assert parsed["lat"] == 35.7274
        assert parsed["lon"] == -78.6960
        assert parsed["alt"] == 100


class TestCoordinateRealWorldDistances:
    """Tests for real-world distance accuracy."""

    def test_1km_distance(self):
        """Test ~1km distance is accurate within 5m."""
        # Two points approximately 1km apart
        c1 = Coordinate(35.7274, -78.6960, 0)
        # Move ~1km north (about 0.009 degrees latitude)
        c2 = Coordinate(35.7364, -78.6960, 0)
        distance = c1.distance(c2)
        # Should be approximately 1000m (within 5m)
        assert 995 < distance < 1005

    def test_100m_north_south_distance(self):
        """Test 100m north-south distance accuracy."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(100, 0, 0)
        c2 = c1 + v
        distance = c1.distance(c2)
        assert 98 < distance < 102

    def test_100m_east_west_distance(self):
        """Test 100m east-west distance accuracy."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(0, 100, 0)
        c2 = c1 + v
        distance = c1.distance(c2)
        assert 98 < distance < 102

