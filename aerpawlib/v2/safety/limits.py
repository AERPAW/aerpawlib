"""
Safety limits for aerpawlib v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SafetyLimits:
    """
    Built-in safety limits (altitude, speed, battery, geofence).

    Used by SafetyMonitor for warnings. Enforcement stays in autopilot/C-VM.
    """

    max_altitude_m: Optional[float] = None
    min_altitude_m: Optional[float] = None
    max_speed_m_s: Optional[float] = None
    min_speed_m_s: Optional[float] = None
    min_battery_percent: Optional[float] = None
    include_geofences: Optional[List[dict]] = None
    exclude_geofences: Optional[List[dict]] = None
