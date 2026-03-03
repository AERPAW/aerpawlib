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

from . import constants
from .aerpaw import AERPAW_Platform
from .exceptions import (
    AerpawlibError,
    ArmError,
    CommandError,
    ConnectionTimeoutError,
    DisarmError,
    HeartbeatLostError,
    InvalidStateError,
    LandingError,
    MultipleInitialStatesError,
    NavigationError,
    NoEntrypointError,
    NoInitialStateError,
    NotArmableError,
    PlanError,
    RTLError,
    RunnerError,
    TakeoffError,
)
from .external import ExternalProcess
from .geofence import do_intersect, inside, read_geofence
from .plan import (
    Waypoint,
    get_location_from_waypoint,
    read_from_plan,
    read_from_plan_complete,
)
from .protocols import GPSProtocol, VehicleProtocol
from .runner import (
    BasicRunner,
    BasicRunnerConfig,
    Runner,
    StateMachine,
    StateMachineConfig,
    StateSpec,
    ZmqStateMachine,
    ZmqStateMachineConfig,
    at_init,
    background,
    entrypoint,
    expose_field_zmq,
    expose_zmq,
    state,
    timed_state,
)
from .types import Attitude, Battery, Coordinate, GPSInfo, VectorNED
from .vehicle import Drone, DummyVehicle, Rover, Vehicle
from .vehicle.base import VehicleTask
from .zmqutil import check_zmq_proxy_reachable, run_zmq_proxy

__all__ = [
    "AerpawlibError",
    "get_location_from_waypoint",
    "ArmError",
    "Attitude",
    "Battery",
    "BasicRunner",
    "Runner",
    "check_zmq_proxy_reachable",
    "CommandError",
    "constants",
    "Coordinate",
    "ConnectionTimeoutError",
    "DisarmError",
    "DummyVehicle",
    "Drone",
    "do_intersect",
    "entrypoint",
    "ExternalProcess",
    "GPSInfo",
    "GPSProtocol",
    "HeartbeatLostError",
    "inside",
    "InvalidStateError",
    "LandingError",
    "MultipleInitialStatesError",
    "NavigationError",
    "NoEntrypointError",
    "NoInitialStateError",
    "NotArmableError",
    "PlanError",
    "read_geofence",
    "read_from_plan",
    "read_from_plan_complete",
    "RTLError",
    "RunnerError",
    "Rover",
    "run_zmq_proxy",
    "StateMachine",
    "state",
    "timed_state",
    "background",
    "at_init",
    "BasicRunnerConfig",
    "StateMachineConfig",
    "StateSpec",
    "ZmqStateMachine",
    "ZmqStateMachineConfig",
    "expose_zmq",
    "expose_field_zmq",
    "TakeoffError",
    "Vehicle",
    "VehicleProtocol",
    "VehicleTask",
    "VectorNED",
    "Waypoint",
]
