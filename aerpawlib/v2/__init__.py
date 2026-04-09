"""
aerpawlib v2 API - async-first vehicle control.

Modern replacement for v1 with single event loop, native async telemetry,
descriptor-based runners, VehicleTask for progress/cancellation, and
built-in safety/connection handling.

Usage:
    from aerpawlib.v2 import Drone, Coordinate, BasicRunner, entrypoint

    class MyMission(BasicRunner):
        @entrypoint
        async def run(self, drone: Drone):
            await drone.takeoff(altitude=10)
            await drone.goto_coordinates(drone.position + VectorNED(20, 0))
            await drone.land()
"""

from .constants import *
from .aerpaw import *
from .exceptions import *
from .external import *
from .geofence import *
from .plan import *
from .protocols import *
from .runner import *
from .testing import *
from .safety import *
from .types import *
from .vehicle import *
from .zmqutil import *
