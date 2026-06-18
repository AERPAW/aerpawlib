import asyncio

from consts import ALT_DIFF, TAKEOFF_ALT, ZMQ_GROUND, ZMQ_TRACER

from aerpawlib.v2 import (
    Coordinate,
    Drone,
    VectorNED,
)
from aerpawlib.v2.runner import (
    ZmqStateMachine,
    expose_field_zmq,
    expose_zmq,
    state,
)


class OrbiterRunner(ZmqStateMachine):
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
        await self.transition_runner(ZMQ_GROUND, "callback_orbiter_ready")
        return "wait_loop"

    @state(name="take_off")
    @expose_zmq("take_off")
    async def state_take_off(self, drone: Drone):
        print("taking off")
        await drone.takeoff(TAKEOFF_ALT + ALT_DIFF)
        await self.transition_runner(ZMQ_GROUND, "callback_orbiter_taken_off")
        return "wait_loop"

    @state(name="next_waypoint")
    @expose_zmq("next_waypoint")
    async def state_next_waypoint(self, drone: Drone):
        coords = await self.query_field(ZMQ_GROUND, "orbiter_next_waypoint")
        await drone.goto_coordinates(coords)
        await self.transition_runner(ZMQ_GROUND, "callback_orbiter_at_waypoint")
        return "wait_loop"

    @state(name="orbit_tracer")
    @expose_zmq("orbit_tracer")
    async def state_orbit_tracer_start(self, drone: Drone):
        self._orbit_coord_center = await self.query_field(ZMQ_TRACER, "position")
        self._orbit_end_position = drone.position
        self._previous_thetas = []
        self._prev_avg_theta = None
        self._initial_theta = None
        return "orbit"

    @state(name="orbit")
    async def state_orbit(self, drone: Drone):
        current_pos = drone.position
        radius_vec = current_pos - self._orbit_coord_center  # points out to drone, use tangent to orbit
        perp_vec = radius_vec.cross_product(VectorNED(0, 0, 1))

        leg_dist = radius_vec.hypot(ignore_down=True)
        d = perp_vec.hypot(ignore_down=True)
        perp_normalized = VectorNED(
            perp_vec.north / d * leg_dist,
            perp_vec.east / d * leg_dist,
        )

        await drone.goto_coordinates(drone.position + perp_normalized)

        for _ in range(3):
            perp_normalized = perp_normalized.rotate_by_angle(90)
            await drone.goto_coordinates(
                drone.position + perp_normalized + perp_normalized,
            )

        perp_normalized = perp_normalized.rotate_by_angle(90)
        await drone.goto_coordinates(drone.position + perp_normalized)

        await self.transition_runner(ZMQ_GROUND, "callback_orbiter_orbit_done")
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
        await self.transition_runner(ZMQ_GROUND, "callback_orbiter_rtl_done")
        return "wait_loop"

    @state(name="land")
    @expose_zmq("land")
    async def state_land(self, drone: Drone):
        await drone.land()
        return
