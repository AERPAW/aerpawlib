"""
SITL Integration tests for complete mission scenarios.

These tests run full mission scripts similar to real experiments.
"""

import pytest
import asyncio
import time

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
]


class TestSquareMission:
    """Test flying a square pattern."""

    @pytest.mark.asyncio
    async def test_square_pattern_flight(self, connected_drone):
        """Test flying in a square pattern."""
        from aerpawlib.v1.util import VectorNED

        # Configuration
        takeoff_alt = 10
        square_size = 20

        # Setup
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(takeoff_alt)

        start_pos = connected_drone.position

        # Define square waypoints
        waypoints = [
            VectorNED(square_size, 0, 0),  # North
            VectorNED(square_size, square_size, 0),  # NE
            VectorNED(0, square_size, 0),  # East
            VectorNED(0, 0, 0),  # Back to start
        ]

        positions_visited = []

        for offset in waypoints:
            target = start_pos + offset
            await connected_drone.goto_coordinates(target, tolerance=3)
            positions_visited.append(connected_drone.position)

        # Verify we visited 4 distinct positions
        assert len(positions_visited) == 4

        # Verify we're back near start
        final_distance = connected_drone.position.ground_distance(start_pos)
        assert final_distance < 5

        # Land
        await connected_drone.land()
        assert connected_drone.armed is False


class TestAltitudeChangeMission:
    """Test changing altitude during flight."""

    @pytest.mark.asyncio
    async def test_altitude_changes(self, connected_drone):
        """Test flying at different altitudes."""
        from aerpawlib.v1.util import Coordinate

        # Setup
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)

        pos = connected_drone.position

        # Go to 20m altitude
        target_20m = Coordinate(pos.lat, pos.lon, 20)
        await connected_drone.goto_coordinates(target_20m, tolerance=3)
        assert connected_drone.position.alt > 18

        # Go to 5m altitude
        target_5m = Coordinate(pos.lat, pos.lon, 5)
        await connected_drone.goto_coordinates(target_5m, tolerance=3)
        assert connected_drone.position.alt < 7

        # Land
        await connected_drone.land()


class TestWaypointMission:
    """Test waypoint-based missions."""

    @pytest.mark.asyncio
    async def test_waypoint_sequence(self, connected_drone):
        """Test flying through a sequence of waypoints."""
        from aerpawlib.v1.util import VectorNED

        # Setup
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(15)

        start = connected_drone.position

        # Create waypoint list
        waypoints = [
            start + VectorNED(30, 0, 0),  # 30m north
            start + VectorNED(30, 30, 0),  # 30m north, 30m east
            start + VectorNED(0, 30, 0),  # 30m east
            start + VectorNED(-30, 30, 0),  # 30m south, 30m east
            start + VectorNED(-30, 0, 0),  # 30m south
            start,  # Home
        ]

        for i, wp in enumerate(waypoints):
            await connected_drone.goto_coordinates(wp, tolerance=4)
            # Verify we reached each waypoint
            dist = connected_drone.position.ground_distance(wp)
            assert dist < 6, f"Failed to reach waypoint {i}: distance={dist}m"

        # Land
        await connected_drone.land()


class TestMissionWithHeading:
    """Test missions with heading control."""

    @pytest.mark.asyncio
    async def test_navigate_with_heading(self, connected_drone):
        """Test navigating while maintaining specific heading."""
        from aerpawlib.v1.util import VectorNED

        # Setup
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)

        start = connected_drone.position

        # Fly east while facing north
        await connected_drone.set_heading(0)  # Face north
        target = start + VectorNED(0, 30, 0)  # Go east
        await connected_drone.goto_coordinates(target, target_heading=0)

        # Should be facing roughly north
        heading = connected_drone.heading
        assert heading < 20 or heading > 340

        # Land
        await connected_drone.land()


class TestEmergencyProcedures:
    """Test emergency procedures."""

    @pytest.mark.asyncio
    async def test_rtl_from_mission(self, connected_drone):
        """Test RTL during a mission."""
        from aerpawlib.v1.util import VectorNED

        # Setup
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(15)

        home = connected_drone.home_coords
        start = connected_drone.position

        # Fly to first waypoint
        wp1 = start + VectorNED(40, 40, 0)
        await connected_drone.goto_coordinates(wp1, tolerance=3)

        # Verify we're away from home
        dist_from_home = connected_drone.position.ground_distance(home)
        assert dist_from_home > 30

        # Trigger RTL (simulating emergency)
        await connected_drone.return_to_launch()

        # Should be disarmed
        assert connected_drone.armed is False


class TestLongDurationMission:
    """Test longer duration missions."""

    @pytest.mark.asyncio
    async def test_extended_flight(self, connected_drone):
        """Test extended flight with multiple operations."""
        from aerpawlib.v1.util import VectorNED

        # Setup
        connected_drone._initialize_prearm(should_postarm_init=True)
        await connected_drone.takeoff(10)

        start = connected_drone.position

        # Perform multiple flight segments
        segments = [
            (VectorNED(20, 0, 0), 0),  # North, face north
            (VectorNED(20, 20, 0), 90),  # NE, face east
            (VectorNED(0, 20, 0), 180),  # E, face south
            (VectorNED(0, 0, 0), 270),  # Home, face west
        ]

        for offset, heading in segments:
            target = start + offset
            await connected_drone.set_heading(heading)
            await connected_drone.goto_coordinates(target, tolerance=3)

            # Small pause between segments
            await asyncio.sleep(1)

        # Verify mission duration
        assert connected_drone._mission_start_time is not None
        duration = time.time() - connected_drone._mission_start_time
        assert duration > 5  # Mission should take at least 5 seconds

        # Land
        await connected_drone.land()
