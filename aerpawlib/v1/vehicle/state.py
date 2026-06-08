"""Thread-safe telemetry state for v1 vehicles."""

from __future__ import annotations

from enum import Enum, auto

from aerpawlib.v1.helpers import ThreadSafeValue

from .telemetry_compat import (
    _AttitudeCompat,
    _BatteryCompat,
    _GPSInfoCompat,
)


class InitPhase(Enum):
    """Private init/arm sequence phase for v1 Vehicle."""

    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETE = auto()


class ThreadSafeVehicleState:
    """Telemetry fields shared between MAVSDK thread and runner thread."""

    def __init__(self) -> None:
        self.armed_state = ThreadSafeValue(initial_value=False)
        self.is_armable_state = ThreadSafeValue(initial_value=False)
        self.health_val = ThreadSafeValue(None)
        self.last_arm_time = ThreadSafeValue(0.0)
        self.position_lat = ThreadSafeValue(0.0)
        self.position_lon = ThreadSafeValue(0.0)
        self.position_alt = ThreadSafeValue(0.0)
        self.position_abs_alt = ThreadSafeValue(0.0)
        self.heading_deg = ThreadSafeValue(0.0)
        self.velocity_ned = ThreadSafeValue([0.0, 0.0, 0.0])
        self.home_position = ThreadSafeValue(None)
        self.home_abs_alt = ThreadSafeValue(0.0)
        self.captured_home = ThreadSafeValue(None)
        self.prearm_checks_ok = ThreadSafeValue(initial_value=False)
        self.ekf_ready = ThreadSafeValue(initial_value=False)
        self.battery_val = ThreadSafeValue(_BatteryCompat())
        self.gps_val = ThreadSafeValue(_GPSInfoCompat())
        self.attitude_val = ThreadSafeValue(_AttitudeCompat())
        self.mode = ThreadSafeValue("UNKNOWN")
        self.armed_telemetry_received = ThreadSafeValue(initial_value=False)
