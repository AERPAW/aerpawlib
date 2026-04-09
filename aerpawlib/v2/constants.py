"""
Constants for aerpawlib v2 API.
"""

import os

# Connection
CONNECTION_TIMEOUT_S = 30.0
"""Max seconds to wait for initial vehicle connection establishment."""
HEARTBEAT_TIMEOUT_S = 5.0
"""Maximum heartbeat gap before vehicle is considered disconnected."""
HEARTBEAT_START_DELAY_S = (
    1.0  # Delay before starting heartbeat monitor after first telemetry
)
"""Delay before heartbeat monitoring begins after first telemetry is received."""
HEARTBEAT_CHECK_INTERVAL_S = 1.0
"""Interval between heartbeat timeout checks in ConnectionHandler."""

# Movement
DEFAULT_POSITION_TOLERANCE_M = 2.0
"""Default position tolerance for determining waypoint arrival."""
DEFAULT_GOTO_TIMEOUT_S = 300.0
"""Default timeout for blocking goto/navigation operations."""
HEADING_TOLERANCE_DEG = 5.0
"""Heading tolerance used by heading-reached checks."""
DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE = 0.95
"""Minimum fraction of requested altitude required to treat takeoff as complete."""
MIN_ARM_TO_TAKEOFF_DELAY_S = 2.0
"""Delay between arm command and takeoff attempt."""
POST_TAKEOFF_STABILIZATION_S = 1.0
"""Stabilization pause after takeoff before issuing follow-up commands."""
ARMING_SEQUENCE_DELAY_S = 2.0
"""Delay between steps in the arm -> guided/offboard -> takeoff sequence."""
POSITION_READY_TIMEOUT_S = 60.0
"""Max wait for valid position estimate before movement commands."""
ARMABLE_TIMEOUT_S = 60.0
"""Max wait for autopilot armable state before failing preflight."""
ARMABLE_STATUS_LOG_INTERVAL_S = 5.0
"""Log cadence while waiting for armable readiness."""
POLLING_DELAY_S = 0.05
"""Generic polling delay used in readiness/movement waits."""
VELOCITY_UPDATE_DELAY_S = 0.05
"""Delay between velocity setpoint updates in velocity control loops."""
VELOCITY_LOOP_HANDOFF_DELAY_S = 0.05
"""Delay before re-entering velocity loop after stopping prior loop iteration."""
OFFBOARD_STOP_SETTLE_DELAY_S = 0.1
"""Delay after sending zero velocity before disabling offboard mode."""

# Validation
MIN_POSITION_TOLERANCE_M = 0.1
"""Minimum accepted position tolerance to reject unrealistic thresholds."""
MAX_POSITION_TOLERANCE_M = 100.0
"""Maximum accepted position tolerance to reject unrealistic thresholds."""

# State machine
STATE_MACHINE_DELAY_S = 0.01
"""Delay between state-machine loop iterations."""

# ZMQ
ZMQ_PROXY_IN_PORT = "5570"
"""Default ZMQ proxy inbound port used for publisher traffic."""
ZMQ_PROXY_OUT_PORT = "5571"
"""Default ZMQ proxy outbound port used for subscriber traffic."""
ZMQ_QUERY_FIELD_TIMEOUT_S = 30.0
"""Timeout for distributed field queries before raising an error."""
ZMQ_TYPE_TRANSITION = "state_transition"
"""Message type for state-transition notifications."""
ZMQ_TYPE_FIELD_REQUEST = "field_request"
"""Message type for distributed field request messages."""
ZMQ_TYPE_FIELD_CALLBACK = "field_callback"
"""Message type for distributed field callback responses."""

# Safety checker
DEFAULT_SAFETY_CHECKER_PORT = 14580
"""Default local port for SafetyCheckerServer client connections."""
SAFETY_CHECKER_REQUEST_TIMEOUT_S = 10.0
"""Timeout for safety-checker request/response operations."""
SERVER_STATUS_REQ = "server_status_req"
"""Request name used for safety-checker liveness checks."""
VALIDATE_WAYPOINT_REQ = "validate_waypoint_req"
"""Request name for waypoint safety validation."""
VALIDATE_CHANGE_SPEED_REQ = "validate_change_speed_req"
"""Request name for speed-change safety validation."""
VALIDATE_TAKEOFF_REQ = "validate_takeoff_req"
"""Request name for takeoff safety validation."""
VALIDATE_LANDING_REQ = "validate_landing_req"
"""Request name for landing safety validation."""

# MAVLink Flags
MAV_SYS_STATUS_PREARM_CHECK = 0x01
"""MAV_SYS_STATUS bit mask for pre-arm check pass/fail state."""

EKF_READY_FLAGS = 831  # EKF fully ready for takeoff
"""
EKF_STATUS_REPORT (ArduPilot) - takeoff readiness
flags bitmask: 831 = all critical EKF estimates good (attitude, velocity, position)
"""

# Rover
ROVER_GUIDED_MODE = 15  # ArduPilot Rover GUIDED mode number
"""ArduPilot Rover GUIDED mode enum value used before arming/navigation."""
ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S = 3.0  # Seconds to wait for mode change
"""Max wait for Rover GUIDED mode switch confirmation."""

# Waypoint and plan (QGroundControl .plan files)
DEFAULT_WAYPOINT_SPEED = 5
"""Default waypoint speed (m/s) applied when plan items omit speed changes."""
PLAN_CMD_TAKEOFF = 22
"""QGroundControl/MAVLink command code for takeoff mission items."""
PLAN_CMD_WAYPOINT = 16
"""QGroundControl/MAVLink command code for standard waypoint mission items."""
PLAN_CMD_RTL = 20
"""QGroundControl/MAVLink command code for return-to-launch mission items."""
PLAN_CMD_SPEED = 178
"""QGroundControl/MAVLink command code for speed-change mission items."""

# AERPAW
DEFAULT_FORWARD_SERVER_IP = os.getenv("AP_EXPENV_OEOCVM_XM", "192.168.32.25")
"""Default AERPAW forward server IP (falls back to C-VM when env var is unset)."""
DEFAULT_FORWARD_SERVER_PORT = 12435
"""Default AERPAW forward server port used for OEO bridge traffic."""


# Network Ports

DEFAULT_MAVSDK_SERVER_PORT = 50051
"""Default MAVSDK gRPC server port"""

DEFAULT_MAV_UDP_PORT = 14550
"""Default MAVLink UDP port"""


# Additional Timing Constants

POST_ARM_STABILIZE_DELAY_S = 0.1
"""Post-arm stabilization delay before takeoff (seconds)"""

HOME_POSITION_TIMEOUT_S = 5.0
"""Timeout for home position readiness (seconds)"""

TAKEOFF_LOG_INTERVAL_S = 2.0
"""Log interval for takeoff progress (seconds)"""

GOTO_LOG_INTERVAL_S = 3.0
"""Log interval for goto progress (seconds)"""

GOTO_POLL_INTERVAL_S = 0.2
"""Polling interval for goto operations (seconds)"""

GOTO_NB_LOG_INTERVAL_S = 5.0
"""Log interval for non-blocking goto (seconds)"""

READY_MOVE_LOG_INTERVAL_S = 10.0
"""Log interval for ready-to-move checks (seconds)"""


# AERPAW Network Timeouts

AERPAW_PING_TIMEOUT_S = 1.0
"""Timeout for AERPAW platform ping (seconds)"""

AERPAW_NOTIFY_TIMEOUT_S = 3.0
"""Timeout for AERPAW notification HTTP requests (seconds)"""


# ZMQ Additional Constants

ZMQ_REACHABILITY_TIMEOUT_S = 2.0
"""Default timeout for ZMQ reachability check (seconds)"""


# GPS Constants

GPS_3D_FIX_TYPE = 3
"""GPS fix type value indicating 3D fix (MAVLink standard)"""


# Battery Constants

DEFAULT_MIN_BATTERY_PERCENT = 10.0
"""Default minimum battery percentage for takeoff validation"""


# Geographic Constants

EARTH_RADIUS_KM = 6378.137
"""Earth radius in kilometers (WGS84)"""

EARTH_RADIUS_M = 6378137.0
"""Earth radius in meters (WGS84)"""

RAD_TO_DEG_FACTOR = 57.2957795
"""Radians to degrees conversion factor (180/π)"""

LAT_M_PER_DEG = 111132.954
"""WGS84 latitude distance calculation coefficients"""
LAT_COEFF_2 = 559.822
"""Cosine-series coefficient used in WGS84 latitude meters/degree approximation."""
LAT_COEFF_4 = 1.175
"""Higher-order cosine coefficient used in WGS84 latitude approximation."""


# MAVLink Message Names

MAVLINK_MSG_COMMAND_LONG = "COMMAND_LONG"
"""MAVLink command message name for rover control"""


# Test Mock Data

MOCK_LAT = 35.727436
"""Mock latitude for testing (Raleigh, NC area)"""

MOCK_LON = -78.696587
"""Mock longitude for testing (Raleigh, NC area)"""
