"""
ZMQ Runner Example (Follower) - modern v2 API

This script demonstrates multi-vehicle coordination using ZMQ.
The follower drone executes remote commands sent by the leader.

Run with:
    aerpawlib --run-proxy  # Run in separate terminal first

    aerpawlib --api-version v2 --script examples/v2/zmq_runner/follower.py \
        --conn udpin://127.0.0.1:14551 --vehicle drone \
        --zmq-identifier follower --zmq-proxy-server 127.0.0.1
"""

import asyncio

from aerpawlib.v2 import Coordinate, Drone, VectorNED
from aerpawlib.v2.runner import ZmqStateMachine, expose_zmq, state


class FollowRunner(ZmqStateMachine):
    """ZMQ StateMachine follower runner."""

    @state(name="launch_wait", first=True)
    async def state_start(self, _):
        return "launch_wait"

    @state(name="takeoff")
    @expose_zmq("takeoff")
    async def state_takeoff(self, drone: Drone):
        print("[follower] taking off")
        await drone.takeoff(altitude=10)
        print("[follower] taken off")
        return "fly_to_waypoint"

    @state(name="fly_to_waypoint")
    async def state_waypoint(self, drone: Drone):
        await drone.goto_coordinates(drone.position + VectorNED(20, 0, 0))
        await asyncio.sleep(5)
        await self.transition_runner("leader", "waypoint_ping")
        return "waypoint_wait"

    @state(name="waypoint_wait")
    async def state_wait_waypoint(self, _):
        return "waypoint_wait"

    @state(name="rtl")
    @expose_zmq("rtl")
    async def state_rtl(self, drone: Drone):
        if drone.home_coords:
            home_coords = Coordinate(
                drone.home_coords.lat,
                drone.home_coords.lon,
                drone.position.alt,
            )
            await drone.goto_coordinates(home_coords)
        await asyncio.sleep(5)
        await self.transition_runner("leader", "last_ping")
        return "wait_last_ping"

    @state("wait_last_ping")
    async def state_wait_last_ping(self, _):
        return "wait_last_ping"

    @state("land")
    @expose_zmq("land")
    async def state_land(self, drone: Drone):
        await drone.land()
        print("[follower] done!")
        return
