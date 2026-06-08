"""
v2 API Example - Figure 8 Pattern

This script demonstrates complex flight patterns using coordinate math.
Flies a figure-8 pattern using waypoints.

Run with:
    aerpawlib --api-version v2 --script examples/v2/figure_eight.py \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

import argparse
import math

from aerpawlib.v2 import BasicRunner, Coordinate, Drone, VectorNED, entrypoint

# Configuration
FLIGHT_ALT = 15  # meters
LOOP_RADIUS = 20  # meters (radius of each loop)
NUM_WAYPOINTS = 16  # points per loop


class FigureEight(BasicRunner):
    """Fly a figure-8 pattern."""

    def __init__(self):
        super().__init__()
        self._radius = LOOP_RADIUS
        self._altitude = FLIGHT_ALT
        self._waypoints_per_loop = NUM_WAYPOINTS

    def initialize_args(self, args: list[str]) -> None:
        """Parse custom arguments."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--radius",
            type=float,
            default=LOOP_RADIUS,
            help="Loop radius in meters",
        )
        parser.add_argument(
            "--altitude",
            type=float,
            default=FLIGHT_ALT,
            help="Flight altitude in meters",
        )
        parsed_args, _ = parser.parse_known_args(args)

        self._radius = parsed_args.radius
        self._altitude = parsed_args.altitude
        print(
            f"[example] Figure-8 config: radius={self._radius}m, alt={self._altitude}m",
        )

    def _generate_figure_8_waypoints(self, center: Coordinate) -> list[Coordinate]:
        """Generate waypoints for a figure-8 pattern."""
        waypoints = []

        # First loop (north of center)
        loop1_center = center + VectorNED(self._radius, 0, 0)
        for i in range(self._waypoints_per_loop):
            angle = (2 * math.pi * i) / self._waypoints_per_loop
            offset = VectorNED(
                self._radius * math.cos(angle),
                self._radius * math.sin(angle),
                0,
            )
            waypoints.append(loop1_center + offset)

        # Second loop (south of center, traced in opposite direction)
        loop2_center = center + VectorNED(-self._radius, 0, 0)
        for i in range(self._waypoints_per_loop):
            # Reverse direction for second loop
            angle = -(2 * math.pi * i) / self._waypoints_per_loop
            offset = VectorNED(
                self._radius * math.cos(angle),
                self._radius * math.sin(angle),
                0,
            )
            waypoints.append(loop2_center + offset)

        return waypoints

    @entrypoint
    async def run(self, drone: Drone):
        """Execute the figure-8 pattern."""
        print(f"[example] Taking off to {self._altitude}m...")
        await drone.takeoff(altitude=self._altitude)

        center = drone.position
        print(f"[example] Center position: {center}")

        # Generate waypoints
        waypoints = self._generate_figure_8_waypoints(center)
        print(f"[example] Generated {len(waypoints)} waypoints")

        # Fly the pattern
        for i, wp in enumerate(waypoints):
            # Set altitude
            target = Coordinate(wp.lat, wp.lon, self._altitude)

            # Calculate progress
            loop_num = 1 if i < self._waypoints_per_loop else 2
            wp_in_loop = i % self._waypoints_per_loop + 1

            print(
                f"[example] Loop {loop_num}, waypoint {wp_in_loop}/{self._waypoints_per_loop}",
            )
            await drone.goto_coordinates(target, tolerance=2)

        # Return to center
        print("[example] Returning to center...")
        await drone.goto_coordinates(center, tolerance=2)

        # Land
        print("[example] Landing...")
        await drone.land()
        print("[example] Figure-8 complete!")
