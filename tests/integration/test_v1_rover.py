"""Integration tests for aerpawlib v1 Rover. Requires
Rover SITL (managed by pytest on port 14560)."""

import pytest

pytestmark = [pytest.mark.integration]


class TestRoverConnection:
    """Rover connection and telemetry."""

    @pytest.mark.asyncio
    async def test_connects(self, connected_rover):
        assert connected_rover.connected is True

    @pytest.mark.asyncio
    async def test_gps_fix(self, connected_rover):
        assert connected_rover.gps.fix_type >= 3

    @pytest.mark.asyncio
    async def test_position_valid(self, connected_rover):
        pos = connected_rover.position
        assert -90 <= pos.lat <= 90 and -180 <= pos.lon <= 180

    @pytest.mark.asyncio
    async def test_battery_valid(self, connected_rover):
        b = connected_rover.battery
        assert b.voltage > 0
        assert 0 <= b.level <= 100

    @pytest.mark.asyncio
    async def test_heading_valid(self, connected_rover):
        h = connected_rover.heading
        assert 0 <= h < 360

    @pytest.mark.asyncio
    async def test_attitude_accessible(self, connected_rover):
        a = connected_rover.attitude
        assert a is not None
        assert isinstance(a.pitch, float)
        assert isinstance(a.yaw, float)
        assert isinstance(a.roll, float)

    @pytest.mark.asyncio
    async def test_gps_satellites_nonnegative(self, connected_rover):
        g = connected_rover.gps
        assert g.satellites_visible >= 0


class TestRoverNavigation:
    """Rover navigation."""

    @pytest.mark.asyncio
    async def test_goto_coordinates(self, connected_rover):
        from aerpawlib.v1.util import VectorNED

        connected_rover._preflight_wait(should_arm=True)
        start = connected_rover.position
        target = start + VectorNED(20, 0)
        await connected_rover.goto_coordinates(target, tolerance=3)
        dist = connected_rover.position.ground_distance(target)
        assert dist < 5


class TestRoverMultiWaypoint:
    """Sequential waypoint navigation for rover."""

    @pytest.mark.asyncio
    async def test_two_sequential_waypoints(self, connected_rover):
        from aerpawlib.v1.util import VectorNED

        connected_rover._preflight_wait(should_arm=True)
        start = connected_rover.position
        wp1 = start + VectorNED(15, 0)
        wp2 = start + VectorNED(15, 15)
        await connected_rover.goto_coordinates(wp1, tolerance=3)
        assert connected_rover.position.ground_distance(wp1) < 5
        await connected_rover.goto_coordinates(wp2, tolerance=3)
        assert connected_rover.position.ground_distance(wp2) < 5

    @pytest.mark.asyncio
    async def test_goto_with_target_heading_does_not_error(self, connected_rover):
        """Rover ignores target_heading but should not raise an error."""
        from aerpawlib.v1.util import VectorNED

        connected_rover._preflight_wait(should_arm=True)
        start = connected_rover.position
        target = start + VectorNED(10, 0)
        # Should complete without error even though heading is ignored for rovers
        await connected_rover.goto_coordinates(target, tolerance=3, target_heading=90)
        dist = connected_rover.position.ground_distance(target)
        assert dist < 5


# MAVSDK reports ArduPilot GUIDED as OFFBOARD.
GUIDED_MODES = {"GUIDED", "OFFBOARD"}


class TestRoverVelocityControl:
    """Velocity control (set_velocity) streams GUIDED setpoints."""

    @pytest.mark.asyncio
    async def test_set_velocity_drives_in_vector_direction(self, connected_rover):
        """An eastward velocity turns the rover east and drives it there."""
        import asyncio as _asyncio

        from aerpawlib.v1.util import VectorNED

        connected_rover._preflight_wait(should_arm=True)
        start = connected_rover.position
        await connected_rover.set_velocity(VectorNED(0, 2))
        await _asyncio.sleep(8)
        velocity = connected_rover.velocity
        moved = connected_rover.position - start
        await connected_rover.set_velocity(VectorNED(0, 0))
        assert velocity.east > 1.0
        assert abs(velocity.north) < 0.7
        assert moved.east > 5
        assert connected_rover.mode in GUIDED_MODES

    @pytest.mark.asyncio
    async def test_zero_velocity_stops_in_guided(self, connected_rover):
        """Stopping holds speed 0 without leaving GUIDED (the AERPAW filter allows only GUIDED)."""
        import asyncio as _asyncio

        from aerpawlib.v1.util import VectorNED

        connected_rover._preflight_wait(should_arm=True)
        await connected_rover.set_velocity(VectorNED(2, 0))
        await _asyncio.sleep(4)
        await connected_rover.set_velocity(VectorNED(0, 0))
        await _asyncio.sleep(4)
        speed = connected_rover.velocity
        assert (speed.north**2 + speed.east**2) ** 0.5 < 0.3
        assert connected_rover.mode in GUIDED_MODES
        assert connected_rover.armed

    @pytest.mark.asyncio
    async def test_duration_stops_rover(self, connected_rover):
        """A timed velocity stops by itself, still in GUIDED; the down component is ignored."""
        import asyncio as _asyncio

        from aerpawlib.v1.util import VectorNED

        connected_rover._preflight_wait(should_arm=True)
        start = connected_rover.position
        await connected_rover.set_velocity(VectorNED(2, 0, 5), duration=4)
        await _asyncio.sleep(9)
        speed = connected_rover.velocity
        moved = connected_rover.position - start
        assert moved.north > 3
        assert (speed.north**2 + speed.east**2) ** 0.5 < 0.3
        assert connected_rover.mode in GUIDED_MODES
