"""
Command validation v2 Example - Use can_takeoff and can_goto before commands.

Run with:
    aerpawlib --api-version v2 --script examples.v2.command_validation_example \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint


class ValidatedMission(BasicRunner):
    """Mission that validates commands before execution."""

    @entrypoint
    async def run(self, drone: Drone):
        ok, msg = await drone.can_takeoff(10)
        if not ok:
            print(f"[example] can_takeoff failed: {msg}")
            return

        await drone.takeoff(altitude=10)
        target = drone.position + VectorNED(20, 0, 0)

        ok, msg = await drone.can_goto(target)
        if not ok:
            print(f"[example] can_goto failed: {msg}")
            await drone.land()
            return

        await drone.goto_coordinates(target)
        await drone.land()
        print("[example] Mission complete")
