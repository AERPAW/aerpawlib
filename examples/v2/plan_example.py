"""Plan v2 Example - Load waypoints from QGroundControl .plan file.

Requires a .plan file (e.g., from QGroundControl). Pass the path with --file.

Run with:
    aerpawlib --api-version v2 --script examples/v2/plan_example.py \
        --vehicle drone --conn udpin://127.0.0.1:14550 \
        --file examples/v2/zmq_preplanned_orbit/orbit.plan
"""

import argparse
from pathlib import Path

from aerpawlib.v2 import BasicRunner, Drone, entrypoint
from aerpawlib.v2.constants import PLAN_CMD_RTL, PLAN_CMD_TAKEOFF, PLAN_CMD_WAYPOINT
from aerpawlib.v2.plan import get_location_from_waypoint, read_from_plan


class PlanMission(BasicRunner):
    """Fly waypoints from a QGroundControl .plan file."""

    def initialize_args(self, args: list[str]) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--file", help="Mission plan file path.", required=True)
        parsed, _ = parser.parse_known_args(args)
        self._plan_path = parsed.file

    @entrypoint
    async def run(self, drone: Drone):
        plan_path = Path(self._plan_path)
        if not plan_path.exists():
            raise FileNotFoundError(
                f"Plan file not found: {plan_path}. Pass --file path/to/mission.plan",
            )

        waypoints = read_from_plan(plan_path)
        print(f"[example] Loaded {len(waypoints)} waypoints")

        for _i, wp in enumerate(waypoints):
            coord = get_location_from_waypoint(wp)
            command, _x, _y, z, _wp_id, _speed = wp
            if command == PLAN_CMD_TAKEOFF:
                await drone.takeoff(altitude=z)
            elif command == PLAN_CMD_WAYPOINT:
                await drone.goto_coordinates(coord)
            elif command == PLAN_CMD_RTL:
                await drone.return_to_launch()
                break

        if PLAN_CMD_RTL not in (w[0] for w in waypoints):
            # home_coords is stored at relative alt 0; goto that coordinate is
            # rejected by the AERPAW checker (min_alt 20). RTL flies home at
            # the current altitude, then lands at the takeoff pad.
            await drone.return_to_launch()
        print("[example] Mission complete")
