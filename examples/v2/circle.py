"""
[NOT SUPPORTED] (uses velocity control)
circle will make a vehicle (drone) fly in a 10m radius circle centered
on where it started. This is a good example of how to use velocity control
and dynamic heading adjustment.

Run with:
    aerpawlib --api-version v2 --script examples/v2/circle.py \
        --vehicle drone --conn udpin://127.0.0.1:14550
"""

import argparse
import asyncio
import math

from aerpawlib.v2 import Coordinate, Drone, StateMachine, VectorNED, state

FLIGHT_ALT = 5  # m
CIRCLE_RAD = 10  # m
CIRCLE_VEL = 1  # m/s
N_LAPS = 1


class Circle(StateMachine):
    """[NOT SUPPORTED] (uses velocity control) Make a vehicle fly in a circular trajectory using velocity control."""

    _target_center: Coordinate
    _point_to_center: bool = False

    def __init__(self):
        super().__init__()
        self._previous_thetas = []
        self._lap = 0
        self._prev_avg_theta = None

    def initialize_args(self, args: list[str]) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--facecenter",
            help="continually look at center of circle",
            action="store_false",
        )
        parsed_args = parser.parse_args(args=args)
        self._point_to_center = not parsed_args.facecenter

    @state(name="start", first=True)
    async def start(self, drone: Drone):
        print("[example] Taking off...")
        await drone.takeoff(altitude=FLIGHT_ALT)
        self._target_center = drone.position
        print(f"[example] Taken off. Center is {self._target_center}")
        return "fly_to_circumference"

    @state(name="fly_to_circumference")
    async def fly_out(self, drone: Drone):
        print("[example] Flying north to the circumference...")
        await drone.goto_coordinates(self._target_center + VectorNED(CIRCLE_RAD, 0, 0))
        return "circularize"

    @state(name="circularize")
    async def circularize(self, drone: Drone):
        current_pos = drone.position
        radius_vec = current_pos - self._target_center  # points out to drone

        # calculate perpendicular/tangent vector by taking cross product w/ down
        perp_vec = radius_vec.cross_product(VectorNED(0, 0, 1))

        # normalize and ignore the height
        hypot = perp_vec.hypot()
        if hypot == 0:
            target_velocity = VectorNED(0, 0, 0)
        else:
            target_velocity = VectorNED(
                perp_vec.north / hypot * CIRCLE_VEL,
                perp_vec.east / hypot * CIRCLE_VEL,
                0,
            )

        # calculate distance from ideal radius for proportional correction
        radius_err = radius_vec.hypot() - CIRCLE_RAD
        rad_correct_vec = (-1 * radius_vec) * radius_err * 0.1
        target_velocity = target_velocity + rad_correct_vec

        await drone.set_velocity(target_velocity)
        await asyncio.sleep(0.1)

        theta = math.atan2(radius_vec.north, radius_vec.east)
        self._previous_thetas.append(theta)
        if len(self._previous_thetas) > 10:
            self._previous_thetas.pop(0)
        avg_theta = sum(self._previous_thetas) / len(self._previous_thetas)
        if self._prev_avg_theta is None:
            self._prev_avg_theta = avg_theta

        if self._point_to_center:
            # point to the center of the circle
            await drone.set_heading(math.degrees(-avg_theta) - 90, blocking=False)

        # this condition fires when going from 3.14 rad -> -3.14 rad
        if self._prev_avg_theta > 0 and avg_theta < 0:
            self._lap += 1
            print(f"[example] Completed lap {self._lap}")
        self._prev_avg_theta = avg_theta

        if self._lap >= N_LAPS:
            return "rtl"

        return "circularize"

    @state(name="rtl")
    async def rtl(self, drone: Drone):
        print("[example] Returning home...")
        await drone.goto_coordinates(self._target_center)
        print("[example] Landing...")
        await drone.land()
        print("[example] Done!")
