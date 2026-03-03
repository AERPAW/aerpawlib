"""
Enhanced v2 Example - PreflightChecks, command validation (can_takeoff, can_goto)

Run with:
    aerpawlib --api-version v2 --script examples.v2.enhanced_example \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint
from aerpawlib.v2.safety import PreflightChecks


class EnhancedMission(BasicRunner):
    """Mission with preflight checks and command validation."""

    @entrypoint
    async def run(self, drone: Drone):
        # Preflight
        ok = await PreflightChecks.run_all(drone)
        if not ok:
            print("[example] Preflight checks failed")
            return

        # Command validation before takeoff
        ok, msg = await drone.can_takeoff(10)
        if not ok:
            print(f"[example] can_takeoff failed: {msg}")
            return

        target = drone.position + VectorNED(20, 0)
        ok, msg = await drone.can_goto(target)
        if not ok:
            print(f"[example] can_goto failed: {msg}")
            return

        await drone.takeoff(altitude=10)
        await drone.goto_coordinates(target)
        await drone.land()
        print("[example] Mission complete")
