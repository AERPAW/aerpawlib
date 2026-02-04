"""
Example demonstrating the aerpawlib v2 API.

This example shows how to use the new Pythonic API for drone control.
To run this example, you need MAVSDK and a simulator (like PX4 SITL) running.

Usage:
    python -m examples.v2.basic_example
"""

import asyncio

from aerpawlib.v2 import (
    BasicRunner,
    Coordinate,
    Drone,
    entrypoint,
    sleep,
    # Logging
    get_logger,
    LogComponent,
)

# Get logger for user scripts (logging is configured by __main__.py)
logger = get_logger(LogComponent.USER)


class SimpleSquareMission(BasicRunner):
    """
    A simple mission that flies a square pattern.

    This demonstrates:
    - Connection and arming
    - Takeoff
    - Navigation using coordinates
    - Using drone state properties
    - Landing
    """

    @entrypoint
    async def fly_square(self, drone: Drone):
        # Connect to the drone
        logger.info("Connecting to drone...")
        await drone.connect()
        logger.info(
            f"Connected! GPS: {drone.gps.quality} ({drone.gps.satellites} satellites)"
        )

        # Wait for GPS lock
        while not drone.gps.has_fix:
            logger.info("Waiting for GPS fix...")
            await sleep(1)

        # Arm and takeoff
        logger.info("Arming...")
        await drone.arm()
        logger.info(f"Armed: {drone.armed}")

        logger.info("Taking off to 10m...")
        await drone.takeoff(altitude=10)
        logger.info(f"Current altitude: {drone.state.altitude:.1f}m")

        # Get current position as starting point
        start = drone.position
        logger.info(f"Starting position: {start}")

        # Define square corners (30m sides)
        corners = [
            start,  # Start
            Coordinate(
                start.latitude + 0.00027, start.longitude, 10
            ),  # ~30m north
            Coordinate(
                start.latitude + 0.00027, start.longitude + 0.00036, 10
            ),  # ~30m east
            Coordinate(
                start.latitude, start.longitude + 0.00036, 10
            ),  # Back south
            start,  # Return to start
        ]

        # Fly the square
        for i, corner in enumerate(corners):
            logger.info(f"Flying to corner {i+1}: {corner}")
            await drone.goto(coordinates=corner)
            logger.info(
                f"  Arrived! Heading: {drone.state.heading:.0f}°, "
                f"Speed: {drone.state.groundspeed:.1f}m/s, "
                f"Battery: {drone.battery.percentage:.0f}%"
            )

        # Land
        logger.info("Landing...")
        await drone.land()
        logger.info("Mission complete!")
