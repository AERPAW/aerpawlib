"""Shared top-level constants for CLI."""

VEHICLE_CONNECT_POLL_INTERVAL_S = 0.1
"""Polling interval while waiting for vehicle objects to report connected. Keep this pretty small to avoid busy-waiting while still reacting quickly (v1 only)"""

RUNNER_DISCONNECT_POLL_INTERVAL_S = 0.1
"""Polling interval used by the connection loss detector within the CLI. This should also be kept pretty small. (v1 only)"""

DEFAULT_CONNECTION_TIMEOUT_S = 30.0
"""Timeout used by the CLI when attempting to connect to the vehicle for the first time."""

DEFAULT_HEARTBEAT_TIMEOUT_S = 5.0
"""Timeout used by the CLI for ending the experiment when the heartbeat drops"""

DEFAULT_MAVSDK_PORT = 50051
"""Default gRPC port passed to embedded MAVSDK server processes."""

DEFAULT_SAFETY_CHECKER_PORT = 14580
"""Default safety-checker port used when connected to AERPAW. (v2 only)"""

# Vehicle type identifiers
VEHICLE_TYPE_GENERIC = "generic"
"""String required to use the Vehicle vehicle class (--vehicle)"""
VEHICLE_TYPE_DRONE = "drone"
"""String required to use the Drone vehicle class (--vehicle)"""
VEHICLE_TYPE_ROVER = "rover"
"""String required to use the Rover vehicle class (--vehicle)"""
VEHICLE_TYPE_NONE = "none"
"""String required to use the DummyVehicle vehicle class (--vehicle)"""

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
