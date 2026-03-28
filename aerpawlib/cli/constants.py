"""Shared top-level constants for CLI.
These constants are API-version agnostic and used by ``aerpawlib.__main__``.
"""

# Polling interval while waiting for v1 vehicle objects to report connected.
# Keep this modest to avoid busy-waiting while still reacting quickly.
VEHICLE_CONNECT_POLL_INTERVAL_S = 0.1

# Polling interval used by the CLI-side v1 connection-loss watcher.
# This drives fail-fast responsiveness when ``vehicle.connected`` drops.
RUNNER_DISCONNECT_POLL_INTERVAL_S = 0.1

# Default timeout used by the CLI for initial vehicle connection attempts.
DEFAULT_CONNECTION_TIMEOUT_S = 30.0

# Default timeout used by the CLI for heartbeat/disconnect fail-fast checks.
DEFAULT_HEARTBEAT_TIMEOUT_S = 5.0

# Default gRPC port passed to embedded MAVSDK server processes.
DEFAULT_MAVSDK_PORT = 50051

# Default safety-checker port used when connected to AERPAW in v2.
DEFAULT_SAFETY_CHECKER_PORT = 14580

# Vehicle type identifiers
VEHICLE_TYPE_GENERIC = "generic"
VEHICLE_TYPE_DRONE = "drone"
VEHICLE_TYPE_ROVER = "rover"
VEHICLE_TYPE_NONE = "none"

# API class names for dynamic import
API_CLASS_VEHICLE = "Vehicle"
API_CLASS_DRONE = "Drone"
API_CLASS_ROVER = "Rover"
API_CLASS_DUMMY_VEHICLE = "DummyVehicle"
API_CLASS_AERPAW_PLATFORM = "AERPAW_Platform"
API_CLASS_RUNNER = "Runner"
API_CLASS_BASIC_RUNNER = "BasicRunner"
API_CLASS_STATE_MACHINE = "StateMachine"
API_CLASS_ZMQ_STATE_MACHINE = "ZmqStateMachine"
API_CLASS_HEARTBEAT_LOST_ERROR = "HeartbeatLostError"

# Vehicle object attribute names (for getattr checks)
VEHICLE_ATTR_CONNECTED = "connected"
VEHICLE_ATTR_INTERNAL_CONNECTED = "_connected"
VEHICLE_ATTR_CLOSED = "_closed"
VEHICLE_ATTR_CONNECTION_ERROR = "_connection_error"

# Event log event names
EVENT_MISSION_START = "mission_start"
EVENT_MISSION_END = "mission_end"
EVENT_CONNECTION_LOST = "connection_lost"

# Logger names
AERPAWLIB_LOGGER_NAME = "aerpawlib"
CYGRPC_LOGGER_NAME = "_cython.cygrpc"
GRPC_CYGRPC_LOGGER_NAME = "grpc._cython.cygrpc"

# Log formatting
LOG_FORMAT_STRING = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_OPEN_MODE = "a"

# Network addresses
LOCALHOST_ADDR = "127.0.0.1"

# Error messages
INVALID_VEHICLE_TYPE_MSG = "Please specify a valid vehicle type"
STANDALONE_MODE_MSG = "--no-aerpaw-environment set: skipping AERPAW platform connection, running in standalone mode."
SAFETY_CHECKER_NOT_PROVIDED_MSG = (
    "Not in AERPAW environment and --safety-checker-port not provided."
)
SAFETY_CHECKER_REQUIRED_MSG_FMT = (
    "AERPAW environment requires SafetyCheckerServer. Connection to %s:%d failed: %s"
)
SAFETY_CHECKER_FALLBACK_MSG_FMT = "SafetyCheckerServer connection failed (%s:%d): %s. Using passthrough (all validations pass)."
VEHICLE_CONNECTION_LOST_MSG_WITH_ERROR_FMT = (
    "Vehicle connection lost ({connection_error})"
)
VEHICLE_CONNECTION_LOST_MSG_WITH_DURATION_FMT = (
    "Vehicle connection lost (disconnected for {age:.1f}s)"
)
AERPAWLIB_CONNECTION_LOST_LOG_MSG = "[aerpawlib] Connection lost"
MULTIPLE_RUNNERS_ERROR_MSG = "You can only define one runner"
NO_RUNNER_FOUND_ERROR_MSG = "No Runner class found in script"

# Log severity levels
LOG_SEVERITY_CRITICAL = "CRITICAL"

# Config argument parsing
CONFIG_ARG_PAIR_SIZE = 2
