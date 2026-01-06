"""
Unit tests for VectorNED class.

Tests all vector operations including arithmetic, rotation, normalization, etc.
"""
import pytest
from aerpawlib.v1.util import VectorNED


class TestVectorNEDCreation:
    """Tests for VectorNED initialization."""

    def test_create_with_all_components(self):
        """Test creating a vector with all three components."""
        v = VectorNED(1.0, 2.0, 3.0)
        assert v.north == 1.0
        assert v.east == 2.0
        assert v.down == 3.0

    def test_create_with_default_down(self):
        """Test creating a vector with default down=0."""
        v = VectorNED(1.0, 2.0)
        assert v.north == 1.0
        assert v.east == 2.0
        assert v.down == 0

    def test_create_zero_vector(self):
        """Test creating a zero vector."""
        v = VectorNED(0, 0, 0)
        assert v.north == 0
        assert v.east == 0
        assert v.down == 0

    def test_create_negative_components(self):
        """Test creating a vector with negative components."""
        v = VectorNED(-5.0, -10.0, -15.0)
        assert v.north == -5.0
        assert v.east == -10.0
        assert v.down == -15.0


class TestVectorNEDArithmetic:
    """Tests for VectorNED arithmetic operations."""

    def test_add_vectors(self):
        """Test adding two vectors."""
        v1 = VectorNED(1, 2, 3)
        v2 = VectorNED(4, 5, 6)
        result = v1 + v2
        assert result.north == 5
        assert result.east == 7
        assert result.down == 9

    def test_add_zero_vector(self):
        """Test adding zero vector returns original."""
        v = VectorNED(1, 2, 3)
        zero = VectorNED(0, 0, 0)
        result = v + zero
        assert result.north == v.north
        assert result.east == v.east
        assert result.down == v.down

    def test_add_invalid_type_raises(self):
        """Test adding non-VectorNED raises TypeError."""
        v = VectorNED(1, 2, 3)
        with pytest.raises(TypeError):
            v + 5
        with pytest.raises(TypeError):
            v + (1, 2, 3)

    def test_subtract_vectors(self):
        """Test subtracting two vectors."""
        v1 = VectorNED(5, 7, 9)
        v2 = VectorNED(1, 2, 3)
        result = v1 - v2
        assert result.north == 4
        assert result.east == 5
        assert result.down == 6

    def test_subtract_self_gives_zero(self):
        """Test subtracting a vector from itself gives zero."""
        v = VectorNED(5, 10, 15)
        result = v - v
        assert result.north == 0
        assert result.east == 0
        assert result.down == 0

    def test_subtract_invalid_type_raises(self):
        """Test subtracting non-VectorNED raises TypeError."""
        v = VectorNED(1, 2, 3)
        with pytest.raises(TypeError):
            v - 5

    def test_multiply_by_scalar(self):
        """Test multiplying vector by scalar."""
        v = VectorNED(2, 3, 4)
        result = v * 2
        assert result.north == 4
        assert result.east == 6
        assert result.down == 8

    def test_multiply_by_zero(self):
        """Test multiplying by zero gives zero vector."""
        v = VectorNED(5, 10, 15)
        result = v * 0
        assert result.north == 0
        assert result.east == 0
        assert result.down == 0

    def test_multiply_by_negative(self):
        """Test multiplying by negative reverses direction."""
        v = VectorNED(1, 2, 3)
        result = v * -1
        assert result.north == -1
        assert result.east == -2
        assert result.down == -3

    def test_rmul_scalar(self):
        """Test scalar * vector (reverse multiply)."""
        v = VectorNED(2, 3, 4)
        result = 3 * v
        assert result.north == 6
        assert result.east == 9
        assert result.down == 12

    def test_multiply_invalid_type_raises(self):
        """Test multiplying by non-numeric raises TypeError."""
        v = VectorNED(1, 2, 3)
        with pytest.raises(TypeError):
            v * "2"


class TestVectorNEDHypot:
    """Tests for VectorNED magnitude (hypot) calculation."""

    def test_hypot_3d(self):
        """Test 3D magnitude calculation."""
        v = VectorNED(3, 4, 0)
        assert v.hypot() == 5.0

    def test_hypot_3d_with_down(self):
        """Test 3D magnitude with down component."""
        v = VectorNED(2, 3, 6)
        assert v.hypot() == 7.0  # sqrt(4 + 9 + 36) = sqrt(49) = 7

    def test_hypot_ignore_down(self):
        """Test 2D magnitude ignoring down."""
        v = VectorNED(3, 4, 100)
        assert v.hypot(ignore_down=True) == 5.0

    def test_hypot_zero_vector(self):
        """Test magnitude of zero vector is zero."""
        v = VectorNED(0, 0, 0)
        assert v.hypot() == 0

    def test_hypot_unit_vectors(self):
        """Test magnitude of unit vectors is 1."""
        assert VectorNED(1, 0, 0).hypot() == 1.0
        assert VectorNED(0, 1, 0).hypot() == 1.0
        assert VectorNED(0, 0, 1).hypot() == 1.0


class TestVectorNEDNorm:
    """Tests for VectorNED normalization."""

    def test_norm_unit_vector(self):
        """Test normalizing a vector gives magnitude 1."""
        v = VectorNED(3, 4, 0)
        normed = v.norm()
        assert abs(normed.hypot() - 1.0) < 1e-10

    def test_norm_preserves_direction(self):
        """Test normalization preserves direction."""
        v = VectorNED(10, 0, 0)
        normed = v.norm()
        assert normed.north == 1.0
        assert normed.east == 0
        assert normed.down == 0

    def test_norm_zero_vector(self):
        """Test normalizing zero vector returns zero vector."""
        v = VectorNED(0, 0, 0)
        normed = v.norm()
        assert normed.north == 0
        assert normed.east == 0
        assert normed.down == 0

    def test_norm_3d_vector(self):
        """Test normalizing 3D vector."""
        v = VectorNED(1, 2, 2)  # magnitude = 3
        normed = v.norm()
        assert abs(normed.north - 1/3) < 1e-10
        assert abs(normed.east - 2/3) < 1e-10
        assert abs(normed.down - 2/3) < 1e-10


class TestVectorNEDRotation:
    """Tests for VectorNED rotation."""

    def test_rotate_90_degrees(self):
        """Test rotating 90 degrees clockwise."""
        v = VectorNED(1, 0, 0)  # Pointing north
        rotated = v.rotate_by_angle(90)
        assert abs(rotated.north) < 1e-10
        assert abs(rotated.east - (-1)) < 1e-10  # Now pointing west

    def test_rotate_180_degrees(self):
        """Test rotating 180 degrees."""
        v = VectorNED(1, 0, 0)
        rotated = v.rotate_by_angle(180)
        assert abs(rotated.north - (-1)) < 1e-10
        assert abs(rotated.east) < 1e-10

    def test_rotate_360_degrees(self):
        """Test rotating 360 degrees returns to original."""
        v = VectorNED(3, 4, 5)
        rotated = v.rotate_by_angle(360)
        assert abs(rotated.north - v.north) < 1e-10
        assert abs(rotated.east - v.east) < 1e-10
        assert rotated.down == v.down  # Down unchanged

    def test_rotate_preserves_down(self):
        """Test rotation doesn't affect down component."""
        v = VectorNED(1, 0, 10)
        rotated = v.rotate_by_angle(45)
        assert rotated.down == 10

    def test_rotate_preserves_magnitude(self):
        """Test rotation preserves vector magnitude."""
        v = VectorNED(3, 4, 0)
        original_mag = v.hypot()
        rotated = v.rotate_by_angle(73)
        assert abs(rotated.hypot() - original_mag) < 1e-10


class TestVectorNEDCrossProduct:
    """Tests for VectorNED cross product."""

    def test_cross_product_orthogonal(self):
        """Test cross product of orthogonal vectors."""
        north = VectorNED(1, 0, 0)
        east = VectorNED(0, 1, 0)
        result = north.cross_product(east)
        # Cross product of N and E should point down (in NED)
        assert abs(result.down - 1) < 1e-10

    def test_cross_product_parallel_is_zero(self):
        """Test cross product of parallel vectors is zero."""
        v1 = VectorNED(1, 0, 0)
        v2 = VectorNED(2, 0, 0)
        result = v1.cross_product(v2)
        assert result.hypot() < 1e-10

    def test_cross_product_invalid_type_raises(self):
        """Test cross product with non-VectorNED raises TypeError."""
        v = VectorNED(1, 2, 3)
        with pytest.raises(TypeError):
            v.cross_product((1, 0, 0))


class TestVectorNEDStr:
    """Tests for VectorNED string representation."""

    def test_str_format(self):
        """Test string format."""
        v = VectorNED(1.5, 2.5, 3.5)
        s = str(v)
        assert "1.5" in s
        assert "2.5" in s
        assert "3.5" in s
        assert s.startswith("(")
        assert s.endswith(")")

