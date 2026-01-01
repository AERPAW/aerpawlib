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
    configure_logging,
    get_logger,
    LogLevel,
    LogComponent,
)

# Configure logging
configure_logging(level=LogLevel.INFO)
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
        logger.info(f"Connected! GPS: {drone.gps.quality} ({drone.gps.satellites} satellites)")

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
            Coordinate(start.latitude + 0.00027, start.longitude, 10),  # ~30m north
            Coordinate(start.latitude + 0.00027, start.longitude + 0.00036, 10),  # ~30m east
            Coordinate(start.latitude, start.longitude + 0.00036, 10),  # Back south
            start,  # Return to start
        ]

        # Fly the square
        for i, corner in enumerate(corners):
            logger.info(f"Flying to corner {i+1}: {corner}")
            await drone.goto(coordinates=corner)
            logger.info(f"  Arrived! Heading: {drone.state.heading:.0f}°, "
                  f"Speed: {drone.state.groundspeed:.1f}m/s, "
                  f"Battery: {drone.battery.percentage:.0f}%")

        # Land
        logger.info("Landing...")
        await drone.land()
        logger.info("Mission complete!")


class TelemetryDemo(BasicRunner):
    """
    Demonstrates accessing drone telemetry through the new API.
    """

    @entrypoint
    async def show_telemetry(self, drone: Drone):
        await drone.connect()

        logger.info("=== Drone Telemetry Demo ===")

        # GPS information
        logger.info("GPS Status:")
        logger.info(f"  Satellites: {drone.gps.satellites}")
        logger.info(f"  Quality: {drone.gps.quality}")
        logger.info(f"  Has Fix: {drone.gps.has_fix}")

        # State information
        logger.info("State:")
        logger.info(f"  Position: {drone.state.position}")
        logger.info(f"  Heading: {drone.state.heading:.1f}°")
        logger.info(f"  Altitude: {drone.state.altitude:.1f}m (MSL)")
        logger.info(f"  Relative Altitude: {drone.state.relative_altitude:.1f}m (AGL)")
        logger.info(f"  Ground Speed: {drone.state.groundspeed:.1f}m/s")
        logger.info(f"  Flight Mode: {drone.state.flight_mode.name}")
        logger.info(f"  Landed State: {drone.state.landed_state.name}")

        # Attitude
        logger.info("Attitude:")
        logger.info(f"  Roll: {drone.state.attitude.roll_degrees:.1f}°")
        logger.info(f"  Pitch: {drone.state.attitude.pitch_degrees:.1f}°")
        logger.info(f"  Yaw: {drone.state.attitude.yaw_degrees:.1f}°")

        # Battery
        logger.info("Battery:")
        logger.info(f"  Voltage: {drone.battery.voltage:.1f}V")
        logger.info(f"  Charge: {drone.battery.percentage:.0f}%")
        logger.info(f"  Current: {drone.battery.current:.1f}A")

        # Vehicle info
        logger.info("Vehicle Info:")
        logger.info(f"  Hardware UUID: {drone.info.hardware_uuid}")
        logger.info(f"  Version: {drone.info.version}")
        logger.info(f"  Vendor: {drone.info.vendor_name}")
        logger.info(f"  Product: {drone.info.product_name}")

        # Convenience properties
        logger.info("Convenience Properties:")
        logger.info(f"  drone.armed: {drone.armed}")
        logger.info(f"  drone.connected: {drone.connected}")
        logger.info(f"  drone.is_armable: {drone.is_armable}")
        logger.info(f"  drone.position: {drone.position}")
        logger.info(f"  drone.heading: {drone.heading}")
        logger.info(f"  drone.altitude: {drone.altitude}")
        logger.info(f"  drone.velocity: {drone.velocity}")
        logger.info(f"  drone.home: {drone.home}")


async def main():
    """Run the example mission."""
    # For simulation, use UDP
    drone = Drone("udp://:14540")

    mission = SimpleSquareMission()
    await mission.fly_square(drone)

    await drone.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

