"""
VehicleTask cancel v2 Example - Start goto, cancel mid-flight (the drone stops
and holds position), then return to the launch point and land.

Run with:
    aerpawlib --api-version v2 --script examples/v2/command_handle_cancel_example.py \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

import asyncio

from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint


class CancelGotoDemo(BasicRunner):
    """Start goto, cancel after a few seconds, then return to launch and land."""

    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=25)
        start = drone.position
        target = start + VectorNED(80, 0, 0)

        print("[example] Starting non-blocking goto...")
        handle = await drone.goto_coordinates(target, tolerance=3, blocking=False)
        assert handle is not None

        # Cancel after ~5 seconds
        for i in range(6):
            await asyncio.sleep(1)
            print(f"[example] Progress: {handle.progress:.0%}")
            if i == 4:
                print("[example] Cancelling goto...")
                handle.cancel()
                break

        await handle.wait_done()
        print("[example] Goto cancelled; drone is holding position in GUIDED")
        # Cancel does not return or land: fly back to the pad and land.
        await drone.return_to_launch()
        print("[example] Mission complete")
