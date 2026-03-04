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
    AerpawConnectionError,
    AerpawlibError,
    ArmError,
    CommandError,
    ConnectionTimeoutError,
    DisarmError,
    HeartbeatLostError,
    InvalidStateError,
    InvalidStateNameError,
    LandingError,
    MultipleInitialStatesError,
    NavigationError,
    NoEntrypointError,
    NoInitialStateError,
    NotArmableError,
    NotConnectedError,
    PlanError,
    PortInUseError,
    RTLError,
    RunnerError,
    StateError,
    TakeoffError,
    UnexpectedDisarmError,
    VelocityError,
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
from .testing import MockVehicle
from .types import Attitude, Battery, Coordinate, GPSInfo, VectorNED
from .vehicle import Drone, DummyVehicle, Rover, Vehicle
from .vehicle.base import VehicleTask
from .zmqutil import check_zmq_proxy_reachable, run_zmq_proxy

__all__ = [
    "AERPAW_Platform",
    "AerpawConnectionError",
    "AerpawlibError",
    "ArmError",
    "Attitude",
    "Battery",
    "BasicRunner",
    "BasicRunnerConfig",
    "CommandError",
    "ConnectionTimeoutError",
    "Coordinate",
    "DisarmError",
    "Drone",
    "DummyVehicle",
    "ExternalProcess",
    "GPSInfo",
    "GPSProtocol",
    "HeartbeatLostError",
    "InvalidStateError",
    "InvalidStateNameError",
    "LandingError",
    "MockVehicle",
    "MultipleInitialStatesError",
    "NavigationError",
    "NoEntrypointError",
    "NoInitialStateError",
    "NotArmableError",
    "NotConnectedError",
    "PlanError",
    "PortInUseError",
    "RTLError",
    "Rover",
    "Runner",
    "RunnerError",
    "StateError",
    "StateMachine",
    "StateMachineConfig",
    "StateSpec",
    "TakeoffError",
    "UnexpectedDisarmError",
    "Vehicle",
    "VehicleProtocol",
    "VehicleTask",
    "VectorNED",
    "VelocityError",
    "Waypoint",
    "ZmqStateMachine",
    "ZmqStateMachineConfig",
    "at_init",
    "background",
    "check_zmq_proxy_reachable",
    "constants",
    "do_intersect",
    "entrypoint",
    "expose_field_zmq",
    "expose_zmq",
    "get_location_from_waypoint",
    "inside",
    "read_from_plan",
    "read_from_plan_complete",
    "read_geofence",
    "run_zmq_proxy",
    "state",
    "timed_state",
]
