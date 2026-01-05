"""
aerpawlib v2 API - MAVSDK-based vehicle control

This module provides a modern, Pythonic API for vehicle control using MAVSDK.
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
    # Config
    AERPAWConfig,
    # Enums
    MessageSeverity,
    # Exceptions
    AERPAWConnectionError,
    AERPAWCheckpointError,
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
)

# Note: safety_checker.py has been removed (was just a backward compatibility re-export wrapper)
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

# Logging
from .logging import (
    # Enums
    LogLevel,
    LogComponent,
    # Configuration
    LoggingConfig,
    LoggingManager,
    # Formatters
    ColoredFormatter,
    JSONFormatter,
    TelemetryFormatter,
    # Handlers
    TelemetryHandler,
    AsyncFileHandler,
    # Data structures
    StructuredLogRecord,
    TelemetryPoint,
    FlightLogMetadata,
    # Flight recording
    FlightDataRecorder,
    # Adapter
    LoggerAdapter,
    # Module functions
    get_manager,
    configure_logging,
    get_logger,
    set_level,
    get_flight_recorder,
    # Decorators
    log_call,
    log_timing,
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
    # Logging - Enums
    "LogLevel",
    "LogComponent",
    # Logging - Configuration
    "LoggingConfig",
    "LoggingManager",
    # Logging - Formatters
    "ColoredFormatter",
    "JSONFormatter",
    "TelemetryFormatter",
    # Logging - Handlers
    "TelemetryHandler",
    "AsyncFileHandler",
    # Logging - Data structures
    "StructuredLogRecord",
    "TelemetryPoint",
    "FlightLogMetadata",
    # Logging - Flight recording
    "FlightDataRecorder",
    # Logging - Adapter
    "LoggerAdapter",
    # Logging - Module functions
    "get_manager",
    "configure_logging",
    "get_logger",
    "set_level",
    "get_flight_recorder",
    # Logging - Decorators
    "log_call",
    "log_timing",
]

