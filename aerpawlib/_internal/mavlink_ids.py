"""Resolve the MAVLink system id for GUIDED-mode commands."""

from __future__ import annotations

import math
import os
from typing import Any

# mavsdk_server default GCS identity. mavlink_direct send fails if we
# impersonate the vehicle (sysid 1); the autopilot accepts COMMAND_LONG from
# this GCS identity.
MAVSDK_GCS_SYSID = 245
MAVSDK_GCS_COMPID = 190


def resolve_gcs_ids() -> tuple[int, int]:
    """Return (sysid, compid) for outbound mavlink_direct commands."""
    sysid = MAVSDK_GCS_SYSID
    compid = MAVSDK_GCS_COMPID
    raw_sys = os.getenv("MAVSDK_SYSID")
    raw_comp = os.getenv("MAVSDK_COMPID")
    if raw_sys:
        try:
            sysid = int(raw_sys)
        except ValueError:
            pass
    if raw_comp:
        try:
            compid = int(raw_comp)
        except ValueError:
            pass
    return sysid, compid


def make_set_mode_message(target_sysid: int, custom_mode: int):
    """Build COMMAND_LONG MAV_CMD_DO_SET_MODE from the MAVSDK GCS identity.

    C-VM filter allows COMMAND_LONG 176 (GUIDED/LAND) only; SET_MODE is not
    on the allow-list. param2 is the ArduPilot custom mode (4 copter, 15 rover).
    """
    import json

    from mavsdk.mavlink_direct import MavlinkMessage
    from pymavlink import mavutil

    gcs_sys, gcs_comp = resolve_gcs_ids()
    fields = {
        "target_system": int(target_sysid),
        "target_component": 1,
        "command": int(mavutil.mavlink.MAV_CMD_DO_SET_MODE),
        "confirmation": 0,
        "param1": float(mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED),
        "param2": float(custom_mode),
        "param3": 0.0,
        "param4": 0.0,
        "param5": 0.0,
        "param6": 0.0,
        "param7": 0.0,
    }
    return MavlinkMessage(
        message_name="COMMAND_LONG",
        system_id=gcs_sys,
        component_id=gcs_comp,
        target_system_id=int(target_sysid),
        target_component_id=1,
        fields_json=json.dumps(fields),
    )


def make_condition_yaw_message(
    target_sysid: int,
    heading_deg: float,
    yaw_speed_deg_s: float = 0.0,
):
    """Build COMMAND_LONG MAV_CMD_CONDITION_YAW from the MAVSDK GCS identity.

    Stays in GUIDED. Do not use offboard for heading on AERPAW.
    param1 = absolute heading (deg), param2 = yaw speed (0 = default),
    param3 = 0 (shortest direction), param4 = 0 (absolute).
    """
    import json

    from mavsdk.mavlink_direct import MavlinkMessage
    from pymavlink import mavutil

    gcs_sys, gcs_comp = resolve_gcs_ids()
    fields = {
        "target_system": int(target_sysid),
        "target_component": 1,
        "command": int(mavutil.mavlink.MAV_CMD_CONDITION_YAW),
        "confirmation": 0,
        "param1": float(heading_deg),
        "param2": float(yaw_speed_deg_s),
        "param3": 0.0,
        "param4": 0.0,
        "param5": 0.0,
        "param6": 0.0,
        "param7": 0.0,
    }
    return MavlinkMessage(
        message_name="COMMAND_LONG",
        system_id=gcs_sys,
        component_id=gcs_comp,
        target_system_id=int(target_sysid),
        target_component_id=1,
        fields_json=json.dumps(fields),
    )


# SET_POSITION_TARGET_LOCAL_NED type_mask bits (MAVLink POSITION_TARGET_TYPEMASK).
_IGNORE_POSITION = 0b000000000111
_IGNORE_VELOCITY = 0b000000111000
_IGNORE_ACCEL = 0b000111000000
_IGNORE_YAW = 0b010000000000
_IGNORE_YAW_RATE = 0b100000000000


def _make_local_ned_setpoint(
    target_sysid: int,
    type_mask: int,
    vx: float = 0.0,
    vy: float = 0.0,
    yaw_rad: float = 0.0,
):
    """Build SET_POSITION_TARGET_LOCAL_NED from the MAVSDK GCS identity.

    The C-VM filter requires position and acceleration to be ignored.
    """
    import json

    from mavsdk.mavlink_direct import MavlinkMessage
    from pymavlink import mavutil

    gcs_sys, gcs_comp = resolve_gcs_ids()
    fields = {
        "time_boot_ms": 0,
        "target_system": int(target_sysid),
        "target_component": 1,
        "coordinate_frame": int(mavutil.mavlink.MAV_FRAME_LOCAL_NED),
        "type_mask": int(type_mask),
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "vx": float(vx),
        "vy": float(vy),
        "vz": 0.0,
        "afx": 0.0,
        "afy": 0.0,
        "afz": 0.0,
        "yaw": float(yaw_rad),
        "yaw_rate": 0.0,
    }
    return MavlinkMessage(
        message_name="SET_POSITION_TARGET_LOCAL_NED",
        system_id=gcs_sys,
        component_id=gcs_comp,
        target_system_id=int(target_sysid),
        target_component_id=1,
        fields_json=json.dumps(fields),
    )


def make_rover_velocity_message(target_sysid: int, north: float, east: float):
    """Velocity-only setpoint; ArduRover steers to the vector's direction.

    Valid only in GUIDED. ArduRover stops if setpoints stop for 3 s.
    """
    return _make_local_ned_setpoint(
        target_sysid,
        _IGNORE_POSITION | _IGNORE_ACCEL | _IGNORE_YAW | _IGNORE_YAW_RATE,
        vx=north,
        vy=east,
    )


def make_rover_stop_message(target_sysid: int, heading_deg: float):
    """Yaw-only setpoint: speed 0 holding ``heading_deg``, staying in GUIDED.

    A zero velocity vector would instead steer toward north (atan2(0, 0)).
    """
    return _make_local_ned_setpoint(
        target_sysid,
        _IGNORE_POSITION | _IGNORE_VELOCITY | _IGNORE_ACCEL | _IGNORE_YAW_RATE,
        yaw_rad=math.radians(heading_deg),
    )


def resolve_mav_sysid(system: Any | None = None, default: int = 1) -> int:
    """Return the vehicle SYSID from env or the MAVSDK system, else *default*.

    Environment (first match wins): ``AP_EXPENV_MAV_SYSID``, ``MAV_SYSID``.
    """
    for key in ("AP_EXPENV_MAV_SYSID", "MAV_SYSID"):
        raw = os.getenv(key)
        if raw:
            try:
                return int(raw)
            except ValueError:
                pass
    if system is not None:
        for attr in ("sysid", "_sysid"):
            val = getattr(system, attr, None)
            if val:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
    return default
