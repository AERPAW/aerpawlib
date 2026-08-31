"""Resolve the MAVLink system id for GUIDED-mode commands."""

from __future__ import annotations

import os
from typing import Any

# mavsdk_server default GCS identity. mavlink_direct send fails if we
# impersonate the vehicle (sysid 1); the autopilot accepts SET_MODE from this
# GCS identity.
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
    """Build a SET_MODE mavlink_direct message from the MAVSDK GCS identity."""
    import json

    from mavsdk.mavlink_direct import MavlinkMessage
    from pymavlink import mavutil

    gcs_sys, gcs_comp = resolve_gcs_ids()
    fields = {
        "target_system": int(target_sysid),
        "base_mode": int(mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED),
        "custom_mode": int(custom_mode),
    }
    return MavlinkMessage(
        message_name="SET_MODE",
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
