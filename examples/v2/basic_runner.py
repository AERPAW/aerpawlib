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
        print("[example] Taking off to 25m...")
        await drone.takeoff(altitude=25)
        start = drone.position
        print("[example] Flying north 10m...")
        await drone.goto_coordinates(start + VectorNED(10, 0, 0))
        print("[example] Returning to takeoff...")
        await drone.goto_coordinates(start)
        print("[example] Landing...")
        await drone.land()
        print("[example] Done!")
