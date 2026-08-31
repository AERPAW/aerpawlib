"""
Example of a script that has a single entry point that doesn't use any kind of
special Runner.
"""

from aerpawlib.v1.runner import BasicRunner, entrypoint
from aerpawlib.v1.util import VectorNED
from aerpawlib.v1.vehicle import Drone


class MyScript(BasicRunner):
    @entrypoint
    async def do_stuff(self, drone: Drone):
        await drone.takeoff(25)
        start = drone.position
        await drone.goto_coordinates(start + VectorNED(10, 0))
        await drone.goto_coordinates(start)
        await drone.land()
