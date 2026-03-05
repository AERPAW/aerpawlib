"""
Plan v2 Example - Load waypoints from QGroundControl .plan file.

Requires a .plan file (e.g. from QGroundControl). Create mission.plan in the script directory
or pass path via --file.

Run with:
    aerpawlib --api-version v2 --script examples/v2/plan_example.py \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

import os

from aerpawlib.v2 import BasicRunner, Drone, entrypoint
from aerpawlib.v2.constants import PLAN_CMD_TAKEOFF, PLAN_CMD_WAYPOINT, PLAN_CMD_RTL
from aerpawlib.v2.plan import get_location_from_waypoint, read_from_plan


class PlanMission(BasicRunner):
    """Fly waypoints from a QGroundControl .plan file."""

    @entrypoint
    async def run(self, drone: Drone):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        plan_path = os.path.join(script_dir, "mission.plan")
        if not os.path.exists(plan_path):
            print(f"[example] No mission.plan at {plan_path}")
            print("[example] Create a .plan file in QGroundControl and save as mission.plan")
            return

        waypoints = read_from_plan(plan_path)
        print(f"[example] Loaded {len(waypoints)} waypoints")

        for i, wp in enumerate(waypoints):
            coord = get_location_from_waypoint(wp)
            command, x, y, z, wp_id, speed = wp
            if command == PLAN_CMD_TAKEOFF:
                await drone.takeoff(altitude=z)
            elif command == PLAN_CMD_WAYPOINT:
                await drone.goto_coordinates(coord)
            elif command == PLAN_CMD_RTL:
                await drone.return_to_launch()
                break

        if PLAN_CMD_RTL not in (w[0] for w in waypoints):
            await drone.land()
        print("[example] Mission complete")
