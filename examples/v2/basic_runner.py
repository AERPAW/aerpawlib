"""
BasicRunner v2 Example - Minimal script with a single entry point.

Run with:
    aerpawlib --api-version v2 --script examples/v2/basic_runner.py \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint


class MyScript(BasicRunner):
    """Minimal BasicRunner example."""

    @entrypoint
    async def do_stuff(self, drone: Drone):
        print("[example] Taking off to 10m...")
        await drone.takeoff(altitude=10)
        print("[example] Flying north 10m...")
        await drone.goto_coordinates(drone.position + VectorNED(10, 0, 0))
        print("[example] Landing...")
        await drone.land()
        print("[example] Done!")
