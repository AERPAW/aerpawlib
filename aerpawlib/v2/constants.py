"""
Constants for aerpawlib v2 API.
"""

import os

# Connection
CONNECTION_TIMEOUT_S = 30.0
HEARTBEAT_TIMEOUT_S = 5.0
HEARTBEAT_START_DELAY_S = (
    1.0  # Delay before starting heartbeat monitor after first telemetry
)
# Interval between heartbeat timeout checks in ConnectionHandler.
HEARTBEAT_CHECK_INTERVAL_S = 1.0

# Movement
DEFAULT_POSITION_TOLERANCE_M = 2.0
DEFAULT_GOTO_TIMEOUT_S = 300.0
HEADING_TOLERANCE_DEG = 5.0
DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE = 0.95
MIN_ARM_TO_TAKEOFF_DELAY_S = 2.0
POST_TAKEOFF_STABILIZATION_S = 1.0
ARMING_SEQUENCE_DELAY_S = 2.0
POSITION_READY_TIMEOUT_S = 60.0
ARMABLE_TIMEOUT_S = 60.0
ARMABLE_STATUS_LOG_INTERVAL_S = 5.0
POLLING_DELAY_S = 0.05
VELOCITY_UPDATE_DELAY_S = 0.05
# Delay before re-entering velocity loop after stopping prior loop iteration.
VELOCITY_LOOP_HANDOFF_DELAY_S = 0.05
# Delay after sending zero velocity before disabling offboard mode.
OFFBOARD_STOP_SETTLE_DELAY_S = 0.1

# Validation
MIN_POSITION_TOLERANCE_M = 0.1
MAX_POSITION_TOLERANCE_M = 100.0

# State machine
STATE_MACHINE_DELAY_S = 0.01

# ZMQ
ZMQ_PROXY_IN_PORT = "5570"
ZMQ_PROXY_OUT_PORT = "5571"
ZMQ_QUERY_FIELD_TIMEOUT_S = 30.0
ZMQ_TYPE_TRANSITION = "state_transition"
ZMQ_TYPE_FIELD_REQUEST = "field_request"
ZMQ_TYPE_FIELD_CALLBACK = "field_callback"

# Safety checker
DEFAULT_SAFETY_CHECKER_PORT = 14580
SAFETY_CHECKER_REQUEST_TIMEOUT_S = 10.0
SERVER_STATUS_REQ = "server_status_req"
VALIDATE_WAYPOINT_REQ = "validate_waypoint_req"
VALIDATE_CHANGE_SPEED_REQ = "validate_change_speed_req"
VALIDATE_TAKEOFF_REQ = "validate_takeoff_req"
VALIDATE_LANDING_REQ = "validate_landing_req"

# MAVLink Flags
MAV_SYS_STATUS_PREARM_CHECK = 0x01

# EKF_STATUS_REPORT (ArduPilot) - takeoff readiness
# flags bitmask: 831 = all critical EKF estimates good (attitude, velocity, position)
EKF_READY_FLAGS = 831  # EKF fully ready for takeoff

# Rover
ROVER_GUIDED_MODE = 15  # ArduPilot Rover GUIDED mode number
ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S = 3.0  # Seconds to wait for mode change

# Waypoint and plan (QGroundControl .plan files)
DEFAULT_WAYPOINT_SPEED = 5
PLAN_CMD_TAKEOFF = 22
PLAN_CMD_WAYPOINT = 16
PLAN_CMD_RTL = 20
PLAN_CMD_SPEED = 178

# AERPAW
DEFAULT_FORWARD_SERVER_IP = os.getenv("AP_EXPENV_OEOCVM_XM", "192.168.32.25")
DEFAULT_FORWARD_SERVER_PORT = 12435
