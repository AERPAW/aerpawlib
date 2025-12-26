"""
aerpawlib v2 API - MAVSDK-based vehicle control

This module provides a modern, Pythonic API for vehicle control using MAVSDK.

Features include:
- Clean property-based state access (drone.state.heading, drone.battery.voltage)
- Intuitive Coordinate-based navigation
- Async-first design with MAVSDK backend
- Simplified mission planning with waypoints
- CommandHandle for non-blocking command execution with progress tracking

Quick Start:
    from aerpawlib.v2 import Drone, Coordinate, BasicRunner, entrypoint

    class MyMission(BasicRunner):
        @entrypoint
        async def run(self, drone: Drone):
            await drone.connect()
            await drone.arm()
            await drone.takeoff(altitude=10)
            await drone.goto(coordinates=Coordinate(51.5, -0.1, 10, "Target"))
            await drone.land()

Non-blocking Commands:
    Commands like goto, takeoff, land, rtl, set_heading, set_velocity, and orbit
    support non-blocking execution via the `wait=False` parameter:

        # Non-blocking goto with progress monitoring
        handle = await drone.goto(latitude=51.5, longitude=-0.1, wait=False)
        while handle.is_running:
            print(f"Distance: {handle.progress.get('distance', '?')}m")
            await asyncio.sleep(1)

        # Cancel a command
        await handle.cancel()

        # Or just await the handle later
        handle = await drone.goto(latitude=51.5, longitude=-0.1, wait=False)
        # ... do other things ...
        await handle  # Wait for completion
"""

from .types import (
    # Core types
    Coordinate,
    VectorNED,
    PositionNED,
    Attitude,
    Waypoint,
    # State containers (for type hints)
    DroneState,
    GPSInfo,
    BatteryInfo,
    DroneInfo,
    FlightInfo,
    # Enums
    FlightMode,
    LandedState,
    # Utility functions
    read_waypoints_from_plan,
)

from .vehicle import (
    Vehicle,
    Drone,
    Rover,
    # Command tracking
    CommandHandle,
    CommandStatus,
    CommandResult,
)

# Safety features (all consolidated in safety.py)
from .safety import (
    # Enums
    SafetyViolationType,
    RequestType,
    VehicleType,
    # Configuration
    SafetyLimits,
    SafetyConfig,
    # Result types
    ValidationResult,
    SafetyCheckResult,
    PreflightCheckResult,
    # Client/Server
    SafetyCheckerClient,
    SafetyCheckerServer,
    # Monitoring
    SafetyMonitor,
    # Validation functions
    validate_coordinate,
    validate_altitude,
    validate_speed,
    validate_velocity,
    validate_timeout,
    validate_tolerance,
    # Server validation functions
    validate_waypoint_with_checker,
    validate_speed_with_checker,
    validate_takeoff_with_checker,
    # Clamping functions
    clamp_speed,
    clamp_velocity,
    # Pre-flight checks
    run_preflight_checks,
    # Exceptions
    SafetyError,
    PreflightCheckError,
    ParameterValidationError,
    SpeedLimitExceededError,
    GeofenceViolationError,
    # Backward compatibility
    SERVER_STATUS_REQ,
    VALIDATE_WAYPOINT_REQ,
    VALIDATE_CHANGE_SPEED_REQ,
    VALIDATE_TAKEOFF_REQ,
    VALIDATE_LANDING_REQ,
    serialize_request,
    serialize_response,
    serialize_msg,
    deserialize_msg,
)

from .runner import (
    # Runners
    Runner,
    BasicRunner,
    StateMachine,
    # Decorators
    entrypoint,
    state,
    timed_state,
    background,
    at_init,
    # Async helpers
    sleep,
    in_background,
)

from .aerpaw import (
    # Main classes
    AERPAWPlatform,
    AERPAW,
    AERPAW_Platform,
    # Config
    AERPAWConfig,
    # Enums
    MessageSeverity,
    # Exceptions
    AERPAWConnectionError,
    AERPAWCheckpointError,
    # Constants (backward compatibility)
    OEO_MSG_SEV_INFO,
    OEO_MSG_SEV_WARN,
    OEO_MSG_SEV_ERR,
    OEO_MSG_SEV_CRIT,
)

from .zmqutil import (
    # Main classes
    ZMQPublisher,
    ZMQSubscriber,
    ZMQMessage,
    ZMQProxyConfig,
    # Enums
    MessageType,
    # Functions
    run_zmq_proxy,
    # Constants (backward compatibility)
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_TYPE_TRANSITION,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_FIELD_CALLBACK,
)

# Note: safety_checker.py now re-exports from safety.py for backward compatibility
# All safety features are consolidated in safety.py

from .geofence import (
    # Main classes
    GeofencePoint,
    Polygon,
    # Functions
    read_geofence,
    is_inside_polygon,
    segments_intersect,
    path_crosses_polygon,
    # Backward compatibility aliases
    readGeofence,
    inside,
    doIntersect,
)

from .exceptions import (
    # Base
    AerpawlibError,
    ErrorSeverity,
    # Connection
    ConnectionError,
    ConnectionTimeoutError,
    HeartbeatLostError,
    ReconnectionError,
    # Command
    CommandError,
    ArmError,
    DisarmError,
    TakeoffError,
    LandingError,
    NavigationError,
    ModeChangeError,
    OffboardError,
    # Timeout
    TimeoutError,
    GotoTimeoutError,
    TakeoffTimeoutError,
    LandingTimeoutError,
    # Abort
    AbortError,
    UserAbortError,
    SafetyAbortError,
    CommandCancelledError,
    # Safety
    SafetyError,
    GeofenceViolationError,
    AltitudeViolationError,
    SpeedViolationError,
    SpeedLimitExceededError,
    ParameterValidationError,
    # Pre-flight
    PreflightError,
    PreflightCheckError,
    GPSError,
    BatteryError,
    NotArmableError,
    # State Machine
    StateMachineError,
    InvalidStateError,
    NoInitialStateError,
    MultipleInitialStatesError,
)

from .testing import (
    MockDrone,
    MockRover,
    MockState,
    MockGPS,
    MockBattery,
)


__all__ = [
    # Core types
    "Coordinate",
    "VectorNED",
    "PositionNED",
    "Attitude",
    "Waypoint",
    # State containers
    "DroneState",
    "GPSInfo",
    "BatteryInfo",
    "DroneInfo",
    "FlightInfo",
    # Enums
    "FlightMode",
    "LandedState",
    # Vehicles
    "Vehicle",
    "Drone",
    "Rover",
    # Command Tracking
    "CommandHandle",
    "CommandStatus",
    "CommandResult",
    # Safety features (all from safety.py)
    "SafetyViolationType",
    "RequestType",
    "VehicleType",
    "SafetyLimits",
    "SafetyConfig",
    "ValidationResult",
    "SafetyCheckResult",
    "PreflightCheckResult",
    "SafetyCheckerClient",
    "SafetyCheckerServer",
    "SafetyMonitor",
    "validate_coordinate",
    "validate_altitude",
    "validate_speed",
    "validate_velocity",
    "validate_timeout",
    "validate_tolerance",
    "validate_waypoint_with_checker",
    "validate_speed_with_checker",
    "validate_takeoff_with_checker",
    "clamp_speed",
    "clamp_velocity",
    "run_preflight_checks",
    "SafetyError",
    "PreflightCheckError",
    "ParameterValidationError",
    "SpeedLimitExceededError",
    "GeofenceViolationError",
    # Runners
    "Runner",
    "BasicRunner",
    "StateMachine",
    # Decorators
    "entrypoint",
    "state",
    "timed_state",
    "background",
    "at_init",
    # Helpers
    "sleep",
    "in_background",
    "read_waypoints_from_plan",
    # AERPAW Platform
    "AERPAWPlatform",
    "AERPAW",
    "AERPAW_Platform",
    "AERPAWConfig",
    "MessageSeverity",
    "AERPAWConnectionError",
    "AERPAWCheckpointError",
    # ZMQ
    "ZMQPublisher",
    "ZMQSubscriber",
    "ZMQMessage",
    "ZMQProxyConfig",
    "MessageType",
    "run_zmq_proxy",
    # Geofence
    "GeofencePoint",
    "Polygon",
    "read_geofence",
    "is_inside_polygon",
    "segments_intersect",
    "path_crosses_polygon",
    # Exceptions - Base
    "AerpawlibError",
    "ErrorSeverity",
    # Exceptions - Connection
    "ConnectionError",
    "ConnectionTimeoutError",
    "HeartbeatLostError",
    "ReconnectionError",
    # Exceptions - Command
    "CommandError",
    "ArmError",
    "DisarmError",
    "TakeoffError",
    "LandingError",
    "NavigationError",
    "ModeChangeError",
    "OffboardError",
    # Exceptions - Timeout
    "TimeoutError",
    "GotoTimeoutError",
    "TakeoffTimeoutError",
    "LandingTimeoutError",
    # Exceptions - Abort
    "AbortError",
    "UserAbortError",
    "SafetyAbortError",
    "CommandCancelledError",
    # Exceptions - Safety
    "SafetyError",
    "GeofenceViolationError",
    "AltitudeViolationError",
    "SpeedViolationError",
    "SpeedLimitExceededError",
    "ParameterValidationError",
    # Exceptions - Pre-flight
    "PreflightError",
    "PreflightCheckError",
    "GPSError",
    "BatteryError",
    "NotArmableError",
    # Exceptions - State Machine
    "StateMachineError",
    "InvalidStateError",
    "NoInitialStateError",
    "MultipleInitialStatesError",
    # Testing
    "MockDrone",
    "MockRover",
    "MockState",
    "MockGPS",
    "MockBattery",
]

