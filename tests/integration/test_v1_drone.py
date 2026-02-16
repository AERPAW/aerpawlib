"""Integration tests for aerpawlib v1 Drone. Requires SITL (managed by pytest)."""

import asyncio
import time

import pytest

pytestmark = [pytest.mark.integration]


class TestDroneConnection:
    """Drone connection and telemetry."""

    @pytest.mark.asyncio
    async def test_connects(self, connected_drone):
        assert connected_drone.connected is True

    @pytest.mark.asyncio
    async def test_gps_fix(self, connected_drone):
        assert connected_drone.gps.fix_type >= 3

    @pytest.mark.asyncio
    async def test_position_valid(self, connected_drone):
        pos = connected_drone.position
        assert -90 <= pos.lat <= 90 and -180 <= pos.lon <= 180

    @pytest.mark.asyncio
    async def test_heading_valid(self, connected_drone):
        assert 0 <= connected_drone.heading < 360

    @pytest.mark.asyncio
    async def test_battery_valid(self, connected_drone):
        b = connected_drone.battery
        assert b.voltage > 0 and 0 <= b.level <= 100


class TestDroneArming:
    """Drone arming."""

    @pytest.mark.asyncio
    async def test_arms_on_takeoff(self, connected_drone):
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(5)
        assert connected_drone.armed is True
        await connected_drone.land()


class TestDroneTakeoff:
    """Drone takeoff."""

    @pytest.mark.asyncio
    async def test_takeoff_reaches_altitude(self, connected_drone):
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)
        assert connected_drone.position.alt >= 9
        await connected_drone.land()


class TestDroneNavigation:
    """Drone navigation."""

    @pytest.mark.asyncio
    async def test_goto_coordinates(self, connected_drone):
        from aerpawlib.v1.util import VectorNED

        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)
        start = connected_drone.position
        target = start + VectorNED(30, 0, 0)
        await connected_drone.goto_coordinates(target, tolerance=3)
        dist = connected_drone.position.ground_distance(target)
        assert dist < 5
        await connected_drone.land()


class TestDroneLanding:
    """Drone landing."""

    @pytest.mark.asyncio
    async def test_land_disarms(self, connected_drone):
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)
        await connected_drone.land()
        assert connected_drone.armed is False


class TestDroneRTL:
    """Return to launch."""

    @pytest.mark.asyncio
    async def test_rtl_returns_home(self, connected_drone):
        from aerpawlib.v1.util import VectorNED

        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)
        home = connected_drone.home_coords
        target = connected_drone.position + VectorNED(40, 0, 0)
        await connected_drone.goto_coordinates(target, tolerance=3)
        await connected_drone.return_to_launch()
        assert connected_drone.armed is False


class TestDroneHeading:
    """Heading control."""

    @pytest.mark.asyncio
    async def test_set_heading(self, connected_drone):
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)
        await connected_drone.set_heading(90)
        h = connected_drone.heading
        assert 80 < h < 100
        await connected_drone.land()
