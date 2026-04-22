"""
Configuration constants for the v1 API.

This module centralizes tunable values used across v1, including connection
timeouts, movement tolerances, MAVLink command identifiers, and AERPAW/
SITL-related defaults.

Capabilities:
- Define shared timeout and polling values used by vehicle and runner logic.
- Define protocol and mode constants used by MAVLink and safety subsystems.
- Define defaults used by CLI/runtime behavior in common mission flows.

Notes:
- Many values are safety-sensitive. Reducing timeouts can make startup and
  telemetry handling less tolerant to transient delays.
"""

import os

# Connection Constants

CONNECTION_TIMEOUT_S = 30.0
"""Maximum time to wait for initial connection to vehicle (seconds)"""

ARMABLE_TIMEOUT_S = 60.0
"""Maximum time to wait for vehicle to become armable (seconds)"""

POSITION_READY_TIMEOUT_S = 60.0
"""
Maximum time to wait for GPS/position ready (seconds)
SITL can report armable before autopilot has valid position for GUIDED mode
"""

POLLING_DELAY_S = 0.01
"""Interval for checking connection state (seconds)"""

HEARTBEAT_CHECK_INTERVAL_S = 1.0
"""Interval between heartbeat timeout checks (seconds)"""

HEARTBEAT_TIMEOUT_S = 1.0
"""Maximum time since last heartbeat before considering vehicle disconnected (seconds)"""


# Safety Initialization Constants


DEFAULT_WAIT_FOR_EXTERNAL_ARM = True
"""Whether to wait for external arming by default (True = safe, False = SITL-friendly)"""

WAITING_FOR_ARM_LOG_INTERVAL_S = 5.0
"""Log interval while waiting for arm (seconds)"""

ARMING_SEQUENCE_DELAY_S = 2.0
"""
Delay between steps of the arm -> guided -> takeoff sequence (seconds)
This provides time for the autopilot to process each command
"""

MIN_ARM_TO_TAKEOFF_DELAY_S = 2.0
"""Minimum time to wait after arming before attempting takeoff (seconds)"""

DEFAULT_RTL_ON_END = True
"""Default RTL on script end behavior (True = safe, returns home)"""

DEFAULT_SKIP_INIT = False
"""Default skip initialization behavior (False = perform all safety checks)"""


# Movement Constants

DEFAULT_POSITION_TOLERANCE_M = 2.0
"""Default tolerance for position reached checks (meters)"""

HEADING_TOLERANCE_DEG = 5.0
"""Tolerance for heading reached checks (degrees)"""

DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE = 0.95
"""
Default minimum altitude tolerance for takeoff (percentage, 0.0-1.0)
Vehicle must reach this fraction of target altitude to consider takeoff complete
"""

DEFAULT_ROVER_POSITION_TOLERANCE_M = 2.1
"""
Default tolerance for rover position checks (meters)
Slightly larger than drone default due to rover GPS accuracy
"""

ROVER_GUIDED_MODE = 15
"""ArduPilot Rover GUIDED mode number (required before arming via MAVLink)"""

ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S = 3.0
"""Seconds to wait for GUIDED mode switch confirmation before continuing"""

DEFAULT_GOTO_TIMEOUT_S = 300.0
"""
Default timeout for goto / navigation commands (seconds)
Used by both drones and rovers when waiting to reach a target coordinate
"""

MAV_SYS_STATUS_PREARM_CHECK = 0x01
"""
MAVLink Flags
Flag for system health: indicates if pre-arm checks are passing
"""

EKF_READY_FLAGS = 831  # EKF fully ready for takeoff
"""
EKF_STATUS_REPORT (ArduPilot) - takeoff readiness
flags bitmask: 831 = all critical EKF estimates good (attitude, velocity, position)
"""


# Timing Constants


POST_TAKEOFF_STABILIZATION_S = 1.0
"""
Post-takeoff stabilization delay (seconds)
Brief pause for controller to settle before next command
"""

INTERNAL_UPDATE_DELAY_S = 0.1
"""Interval for internal state update loop (seconds)"""

STATE_MACHINE_DELAY_S = 0.01
"""State machine delay between state transitions (seconds)"""

VELOCITY_UPDATE_DELAY_S = 0.05
"""Delay for velocity command update loop (seconds)"""

OFFBOARD_STOP_SETTLE_DELAY_S = 0.1
"""
Delay after sending zero-velocity before stopping offboard mode (seconds).
Gives the autopilot one control cycle to consume the stop command.
"""

ARMABLE_STATUS_LOG_INTERVAL_S = 5.0
"""Logging interval when waiting for armable state (seconds)"""


# Verbose Logging Constants

VERBOSE_LOG_FILE_PREFIX = "aerpawlib_vehicle_dump"
"""Default prefix for verbose log files"""

VERBOSE_LOG_DELAY_S = 0.1
"""Default delay between verbose log entries (seconds)"""

STRUCTURED_TELEMETRY_INTERVAL_S = 5.0
"""Interval between JSONL telemetry snapshots for --structured-log (v1)"""


# Validation Limits

MIN_POSITION_TOLERANCE_M = 0.1
"""
Minimum acceptable position tolerance (meters)
Prevents users from setting unrealistically tight tolerances
"""

MAX_POSITION_TOLERANCE_M = 100.0
"""Maximum acceptable position tolerance (meters)"""


# AERPAW Platform Constants

DEFAULT_CVM_IP = "192.168.32.25"
"""Default Controller VM (C-VM) address and port"""
DEFAULT_CVM_PORT = 12435
"""Default Controller VM (C-VM) service port."""

DEFAULT_FORWARD_SERVER_IP = os.getenv("AP_EXPENV_OEOCVM_XM", "192.168.32.25")
"""connect to OEO-CONSOLE, or default to C-VM (will only work on portable nodes)"""
DEFAULT_FORWARD_SERVER_PORT = 12435
"""Default forwarder port for AERPAW bridge traffic."""

DEFAULT_HUMAN_READABLE_AGENT_ID = os.getenv("AP_EXPENV_THIS_CONTAINER_EXP_NODE_NUM")
"""Human-readable node identifier from AERPAW experiment environment."""

OEO_MSG_SEV_INFO = "INFO"
"""OEO Log Severities"""
OEO_MSG_SEV_WARN = "WARNING"
"""Warning severity label for OEO logging."""
OEO_MSG_SEV_ERR = "ERROR"
"""Error severity label for OEO logging."""
OEO_MSG_SEV_CRIT = "CRITICAL"
"""Critical severity label for OEO logging."""
OEO_MSG_SEVS = [
    OEO_MSG_SEV_INFO,
    OEO_MSG_SEV_WARN,
    OEO_MSG_SEV_ERR,
    OEO_MSG_SEV_CRIT,
]
"""Ordered list of supported OEO severity labels."""


# ZMQ Constants

ZMQ_PROXY_IN_PORT = "5570"
"""Default ZMQ proxy ports"""
ZMQ_PROXY_OUT_PORT = "5571"
"""Outbound ZMQ proxy port used for subscriber traffic."""

ZMQ_TYPE_TRANSITION = "state_transition"
"""ZMQ Message Types"""
ZMQ_TYPE_FIELD_REQUEST = "field_request"
"""Message type for distributed field requests over ZMQ."""
ZMQ_TYPE_FIELD_CALLBACK = "field_callback"
"""Message type for distributed field callback responses over ZMQ."""

ZMQ_QUERY_FIELD_TIMEOUT_S = 30.0
"""Timeout for ZMQ field query (seconds) - prevents indefinite block if peer never replies"""


# Safety Checker Constants

SAFETY_CHECKER_REQUEST_TIMEOUT_S = 10.0
"""Timeout for safety checker client send/recv (seconds) - prevents indefinite block if server is down"""

SERVER_STATUS_REQ = "server_status_req"
"""Safety Checker Request Types"""
VALIDATE_WAYPOINT_REQ = "validate_waypoint_req"
"""Request name for waypoint safety validation."""
VALIDATE_CHANGE_SPEED_REQ = "validate_change_speed_req"
"""Request name for speed-change safety validation."""
VALIDATE_TAKEOFF_REQ = "validate_takeoff_req"
"""Request name for takeoff safety validation."""
VALIDATE_LANDING_REQ = "validate_landing_req"
"""Request name for landing safety validation."""


# Waypoint and Plan Constants

DEFAULT_WAYPOINT_SPEED = 5
"""Default waypoint speed (m/s)"""

PLAN_CMD_TAKEOFF = 22
"""MAVLink/Plan Commands"""
PLAN_CMD_WAYPOINT = 16
"""QGroundControl/MAVLink command code for waypoint mission items."""
PLAN_CMD_RTL = 20
"""QGroundControl/MAVLink command code for return-to-launch mission items."""
PLAN_CMD_SPEED = 178
"""QGroundControl/MAVLink command code for speed mission items."""


# Vehicle Type Identifiers

VEHICLE_TYPE_COPTER = "copter"
"""Vehicle type string for copter/drone in safety validation"""
VEHICLE_TYPE_ROVER = "rover"
"""Vehicle type string for rover in safety validation"""


# Additional Timing Constants

TELEMETRY_SUBSCRIPTION_TIMEOUT_S = 5.0
"""Timeout for telemetry subscription (seconds)"""

MAVSDK_THREAD_SHUTDOWN_TIMEOUT_S = 5.0
"""Timeout for MAVSDK thread shutdown (seconds)"""

MAVLINK_COMMAND_TIMEOUT_S = 5.0
"""Timeout for MAVLink command execution (seconds)"""


# AERPAW Network Timeouts

AERPAW_PING_TIMEOUT_S = 1
"""Timeout for AERPAW platform ping (seconds)"""

AERPAW_OEO_MSG_TIMEOUT_S = 3
"""Timeout for AERPAW OEO message HTTP requests (seconds)"""

AERPAW_CHECKPOINT_TIMEOUT_S = 5
"""Timeout for AERPAW checkpoint HTTP requests (seconds)"""


# Retry Configuration

MAX_TELEMETRY_RETRIES = 3
"""Maximum number of retries for telemetry subscription"""


# ZMQ Additional Constants

ZMQ_PROXY_CHECK_TIMEOUT_S = 2.0
"""Default timeout for ZMQ proxy reachability check (seconds)"""


# GPS Constants

GPS_3D_FIX_TYPE = 3
"""GPS fix type value indicating 3D fix (MAVLink standard)"""


# Safety Server Constants

DEFAULT_SAFETY_SERVER_PORT = 14580
"""Default port for safety checker server"""


# Geographic Constants

EARTH_RADIUS_KM = 6378.137
"""Earth radius in kilometers (WGS84)"""

EARTH_RADIUS_M = 6378137.0
"""Earth radius in meters (WGS84)"""

RAD_TO_DEG_FACTOR = 57.2957795
"""Radians to degrees conversion factor (180/π)"""

COORDINATE_EPSILON = 1e-10
"""Coordinate equality epsilon for floating point comparison"""

LAT_M_PER_DEG = 111132.954
"""WGS84 latitude distance calculation coefficients"""
LAT_COEFF_2 = 559.822
"""Cosine-series coefficient used in WGS84 latitude meters/degree approximation."""
LAT_COEFF_4 = 1.175
"""Higher-order cosine coefficient used in WGS84 latitude approximation."""


# MAVLink Message Names

MAVLINK_MSG_COMMAND_LONG = "COMMAND_LONG"
"""MAVLink command message name for rover control"""

GUIDED_MODE_NAME = "OFFBOARD"
"""Rover mode name string"""
