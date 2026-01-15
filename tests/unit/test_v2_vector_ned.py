"""
Unit tests for v2 VectorNED class.

Tests all vector operations including arithmetic, rotation, normalization, etc.
"""

import pytest
import math
from aerpawlib.v2.types import VectorNED


class TestVectorNEDCreation:
    """Tests for VectorNED initialization."""

    def test_create_with_all_components(self):
        """Test creating a vector with all three components."""
        v = VectorNED(north=1.0, east=2.0, down=3.0)
        assert v.north == 1.0
        assert v.east == 2.0
        assert v.down == 3.0

    def test_create_with_defaults(self):
        """Test creating a vector with default values."""
        v = VectorNED()
        assert v.north == 0.0
        assert v.east == 0.0
        assert v.down == 0.0

    def test_create_zero_vector(self):
        """Test creating a zero vector."""
        v = VectorNED(0, 0, 0)
        assert v.north == 0
        assert v.east == 0
        assert v.down == 0

    def test_create_negative_components(self):
        """Test creating a vector with negative components."""
        v = VectorNED(north=-5.0, east=-10.0, down=-15.0)
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

    def test_multiply_by_scalar(self):
        """Test multiplying vector by scalar."""
        v = VectorNED(2, 3, 4)
        result = v * 2
        assert result.north == 4
        assert result.east == 6
        assert result.down == 8

    def test_rmul_scalar(self):
        """Test scalar * vector (reverse multiply)."""
        v = VectorNED(2, 3, 4)
        result = 3 * v
        assert result.north == 6
        assert result.east == 9
        assert result.down == 12

    def test_negate_vector(self):
        """Test negating a vector."""
        v = VectorNED(1, 2, 3)
        result = -v
        assert result.north == -1
        assert result.east == -2
        assert result.down == -3


class TestVectorNEDMagnitude:
    """Tests for VectorNED magnitude calculation."""

    def test_magnitude_3d(self):
        """Test 3D magnitude calculation."""
        v = VectorNED(3, 4, 0)
        assert v.magnitude() == 5.0

    def test_magnitude_3d_with_down(self):
        """Test 3D magnitude with down component."""
        v = VectorNED(2, 3, 6)
        assert v.magnitude() == 7.0  # sqrt(4 + 9 + 36) = sqrt(49) = 7

    def test_magnitude_ignore_vertical(self):
        """Test 2D magnitude ignoring vertical."""
        v = VectorNED(3, 4, 100)
        assert v.magnitude(ignore_vertical=True) == 5.0

    def test_magnitude_zero_vector(self):
        """Test magnitude of zero vector is zero."""
        v = VectorNED(0, 0, 0)
        assert v.magnitude() == 0


class TestVectorNEDNormalize:
    """Tests for VectorNED normalization."""

    def test_normalize_gives_unit_length(self):
        """Test normalizing a vector gives magnitude 1."""
        v = VectorNED(3, 4, 0)
        normed = v.normalize()
        assert abs(normed.magnitude() - 1.0) < 1e-10

    def test_normalize_preserves_direction(self):
        """Test normalization preserves direction."""
        v = VectorNED(10, 0, 0)
        normed = v.normalize()
        assert normed.north == 1.0
        assert normed.east == 0
        assert normed.down == 0

    def test_normalize_zero_vector(self):
        """Test normalizing zero vector returns zero vector."""
        v = VectorNED(0, 0, 0)
        normed = v.normalize()
        assert normed.north == 0
        assert normed.east == 0
        assert normed.down == 0


class TestVectorNEDRotation:
    """Tests for VectorNED rotation."""

    def test_rotate_90_degrees(self):
        """Test rotating 90 degrees."""
        v = VectorNED(1, 0, 0)  # Pointing north
        rotated = v.rotate_by_angle(90)
        assert abs(rotated.north) < 1e-10
        assert abs(rotated.east - (-1)) < 1e-10

    def test_rotate_180_degrees(self):
        """Test rotating 180 degrees."""
        v = VectorNED(1, 0, 0)
        rotated = v.rotate_by_angle(180)
        assert abs(rotated.north - (-1)) < 1e-10
        assert abs(rotated.east) < 1e-10

    def test_rotate_preserves_down(self):
        """Test rotation doesn't affect down component."""
        v = VectorNED(1, 0, 10)
        rotated = v.rotate_by_angle(45)
        assert rotated.down == 10


class TestVectorNEDCrossProduct:
    """Tests for VectorNED cross product."""

    def test_cross_product_orthogonal(self):
        """Test cross product of orthogonal vectors."""
        north = VectorNED(1, 0, 0)
        east = VectorNED(0, 1, 0)
        result = north.cross_product(east)
        assert abs(result.down - 1) < 1e-10

    def test_cross_product_invalid_type_raises(self):
        """Test cross product with non-VectorNED raises TypeError."""
        v = VectorNED(1, 2, 3)
        with pytest.raises(TypeError):
            v.cross_product((1, 0, 0))


class TestVectorNEDDotProduct:
    """Tests for VectorNED dot product."""

    def test_dot_product_orthogonal(self):
        """Test dot product of orthogonal vectors is zero."""
        v1 = VectorNED(1, 0, 0)
        v2 = VectorNED(0, 1, 0)
        assert v1.dot_product(v2) == 0

    def test_dot_product_parallel(self):
        """Test dot product of parallel vectors."""
        v1 = VectorNED(1, 0, 0)
        v2 = VectorNED(2, 0, 0)
        assert v1.dot_product(v2) == 2


class TestVectorNEDHeading:
    """Tests for VectorNED heading calculation."""

    def test_heading_north(self):
        """Test heading of north-pointing vector."""
        v = VectorNED(1, 0, 0)
        assert abs(v.heading() - 0) < 1 or abs(v.heading() - 360) < 1

    def test_heading_east(self):
        """Test heading of east-pointing vector."""
        v = VectorNED(0, 1, 0)
        assert abs(v.heading() - 90) < 1

    def test_heading_south(self):
        """Test heading of south-pointing vector."""
        v = VectorNED(-1, 0, 0)
        assert abs(v.heading() - 180) < 1


class TestVectorNEDRepr:
    """Tests for VectorNED string representation."""

    def test_repr_format(self):
        """Test repr format."""
        v = VectorNED(1.5, 2.5, 3.5)
        s = repr(v)
        assert "VectorNED" in s
        assert "1.5" in s
        assert "2.5" in s
        assert "3.5" in s
