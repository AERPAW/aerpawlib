import asyncio

from consts import TAKEOFF_ALT, ZMQ_GROUND

from aerpawlib.v2 import Coordinate, Drone
from aerpawlib.v2.runner import (
    ZmqStateMachine,
    expose_field_zmq,
    expose_zmq,
    state,
)


class TracerRunner(ZmqStateMachine):
    @expose_field_zmq("position")
    async def get_drone_position(self, drone: Drone):
        return drone.position

    @state(name="wait_loop")
    async def state_wait_loop(self, _):
        # used to continually wait for an action to come in
        await asyncio.sleep(0.1)
        return "wait_loop"

    @state(name="report_ready", first=True)
    async def state_report_ready(self, _):
        await self.transition_runner(ZMQ_GROUND, "callback_tracer_ready")
        return "wait_loop"

    @state(name="take_off")
    @expose_zmq("take_off")
    async def state_take_off(self, drone: Drone):
        print("taking off")
        await drone.takeoff(TAKEOFF_ALT)
        await self.transition_runner(ZMQ_GROUND, "callback_tracer_taken_off")
        return "wait_loop"

    @state(name="next_waypoint")
    @expose_zmq("next_waypoint")
    async def state_next_waypoint(self, drone: Drone):
        coords = await self.query_field(ZMQ_GROUND, "tracer_next_waypoint")
        await drone.goto_coordinates(coords)
        await self.transition_runner(ZMQ_GROUND, "callback_tracer_at_waypoint")
        return "wait_loop"

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
        await self.transition_runner(ZMQ_GROUND, "callback_tracer_rtl_done")
        return "wait_loop"

    @state(name="land")
    @expose_zmq("land")
    async def state_land(self, drone: Drone):
        await drone.land()
        return
