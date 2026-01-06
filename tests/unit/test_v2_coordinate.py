"""
Unit tests for v2 Coordinate class.

Tests coordinate operations including distance, bearing, arithmetic with vectors, etc.
"""
import pytest
from aerpawlib.v2.types import Coordinate, VectorNED


class TestCoordinateCreation:
    """Tests for Coordinate initialization."""

    def test_create_with_all_components(self):
        """Test creating a coordinate with lat, lon, alt."""
        c = Coordinate(latitude=35.7274, longitude=-78.6960, altitude=100.0)
        assert c.latitude == 35.7274
        assert c.longitude == -78.6960
        assert c.altitude == 100.0

    def test_create_with_name(self):
        """Test creating a coordinate with a name."""
        c = Coordinate(35.7274, -78.6960, 100.0, name="Test Location")
        assert c.name == "Test Location"

    def test_create_with_default_alt(self):
        """Test creating a coordinate with default alt=0."""
        c = Coordinate(35.7274, -78.6960)
        assert c.altitude == 0

    def test_property_aliases(self):
        """Test lat/lon/alt property aliases."""
        c = Coordinate(35.7274, -78.6960, 100.0)
        assert c.lat == c.latitude
        assert c.lon == c.longitude
        assert c.alt == c.altitude

    def test_property_setters(self):
        """Test lat/lon/alt property setters."""
        c = Coordinate(0, 0, 0)
        c.lat = 35.0
        c.lon = -78.0
        c.alt = 50.0
        assert c.latitude == 35.0
        assert c.longitude == -78.0
        assert c.altitude == 50.0


class TestCoordinateDistance:
    """Tests for Coordinate distance calculations."""

    def test_distance_same_point(self):
        """Test distance between same point is zero."""
        c = Coordinate(35.7274, -78.6960, 100)
        assert c.distance_to(c) == 0

    def test_distance_nearby_points(self):
        """Test distance calculation for nearby points."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7284, -78.6960, 0)  # ~111m north
        distance = c1.distance_to(c2)
        assert 100 < distance < 120

    def test_distance_includes_altitude(self):
        """Test that distance includes altitude difference."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6960, 100)
        distance = c1.distance_to(c2)
        assert abs(distance - 100) < 1

    def test_ground_distance_ignores_altitude(self):
        """Test ground_distance ignores altitude."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6960, 100)
        ground_dist = c1.ground_distance_to(c2)
        assert ground_dist < 1

    def test_distance_invalid_type_raises(self):
        """Test distance with non-Coordinate raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c.distance_to((35.7284, -78.6960, 0))

    def test_distance_is_symmetric(self):
        """Test distance(a, b) == distance(b, a)."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7384, -78.6860, 50)
        assert abs(c1.distance_to(c2) - c2.distance_to(c1)) < 0.001


class TestCoordinateBearing:
    """Tests for Coordinate bearing calculations."""

    def test_bearing_north(self):
        """Test bearing to point directly north is ~0°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7374, -78.6960, 0)  # North
        bearing = c1.bearing_to(c2)
        assert abs(bearing) < 1 or abs(bearing - 360) < 1

    def test_bearing_east(self):
        """Test bearing to point directly east is ~90°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.6860, 0)  # East
        bearing = c1.bearing_to(c2)
        assert abs(bearing - 90) < 1

    def test_bearing_south(self):
        """Test bearing to point directly south is ~180°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7174, -78.6960, 0)  # South
        bearing = c1.bearing_to(c2)
        assert abs(bearing - 180) < 1

    def test_bearing_west(self):
        """Test bearing to point directly west is ~270°."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7274, -78.7060, 0)  # West
        bearing = c1.bearing_to(c2)
        assert abs(bearing - 270) < 1

    def test_bearing_invalid_type_raises(self):
        """Test bearing with non-Coordinate raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c.bearing_to((35.7374, -78.6960, 0))


class TestCoordinateArithmetic:
    """Tests for Coordinate arithmetic with VectorNED."""

    def test_add_vector_north(self):
        """Test adding a northward vector moves coordinate north."""
        c = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(100, 0, 0)  # 100m north
        result = c + v
        assert result.latitude > c.latitude
        assert abs(result.longitude - c.longitude) < 1e-6
        assert result.altitude == c.altitude

    def test_add_vector_east(self):
        """Test adding an eastward vector moves coordinate east."""
        c = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(0, 100, 0)  # 100m east
        result = c + v
        assert abs(result.latitude - c.latitude) < 1e-6
        assert result.longitude > c.longitude

    def test_add_vector_down_decreases_alt(self):
        """Test adding a downward vector decreases altitude."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(0, 0, 50)  # 50m down
        result = c + v
        assert result.altitude == 50

    def test_add_invalid_type_raises(self):
        """Test adding non-VectorNED raises TypeError."""
        c = Coordinate(35.7274, -78.6960, 0)
        with pytest.raises(TypeError):
            c + (100, 50, 0)

    def test_subtract_vector(self):
        """Test subtracting a vector."""
        c = Coordinate(35.7274, -78.6960, 100)
        v = VectorNED(100, 0, 0)
        result = c - v
        assert result.latitude < c.latitude

    def test_subtract_coordinates_gives_vector(self):
        """Test subtracting coordinates gives a VectorNED."""
        c1 = Coordinate(35.7274, -78.6960, 100)
        c2 = Coordinate(35.7274, -78.6960, 0)
        result = c1 - c2
        assert isinstance(result, VectorNED)


class TestCoordinateJson:
    """Tests for Coordinate JSON serialization."""

    def test_to_json(self):
        """Test to_json returns valid JSON string."""
        import json
        c = Coordinate(35.7274, -78.6960, 100)
        json_str = c.to_json()
        parsed = json.loads(json_str)
        assert parsed["latitude"] == 35.7274
        assert parsed["longitude"] == -78.6960
        assert parsed["altitude"] == 100

    def test_from_json(self):
        """Test from_json creates Coordinate from JSON."""
        json_str = '{"latitude": 35.7274, "longitude": -78.6960, "altitude": 100}'
        c = Coordinate.from_json(json_str)
        assert c.latitude == 35.7274
        assert c.longitude == -78.6960
        assert c.altitude == 100


class TestCoordinateRepr:
    """Tests for Coordinate string representation."""

    def test_repr_format(self):
        """Test repr format."""
        c = Coordinate(35.7274, -78.6960, 100.5)
        s = repr(c)
        assert "Coordinate" in s
        assert "35.7274" in s


class TestCoordinateRealWorldDistances:
    """Tests for real-world distance accuracy."""

    def test_1km_distance(self):
        """Test ~1km distance is accurate within 5m."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        c2 = Coordinate(35.7364, -78.6960, 0)
        distance = c1.distance_to(c2)
        assert 995 < distance < 1005

    def test_100m_north_south_distance(self):
        """Test 100m north-south distance accuracy."""
        c1 = Coordinate(35.7274, -78.6960, 0)
        v = VectorNED(100, 0, 0)
        c2 = c1 + v
        distance = c1.distance_to(c2)
        assert 98 < distance < 102

