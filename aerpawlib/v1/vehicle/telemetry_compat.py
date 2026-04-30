"""
Telemetry compatibility wrappers for v1 vehicles.

This module defines lightweight adapter classes that preserve legacy
DroneKit-style telemetry attribute layouts used by older scripts.

Capabilities:
- Expose compatibility wrappers for battery, GPS, attitude, and version data.
- Provide stable, lightweight containers for migrated call sites.

Notes:
- These wrappers are compatibility-focused and intentionally minimal.
"""
from __future__ import annotations


class _BatteryCompat:
    """
    Compatibility wrapper to match dronekit.Battery interface.

    Attributes:
        voltage: Battery voltage in volts
        current: Battery current draw in amps
        level: Battery level as percentage (0-100)
    """

    __slots__ = ("voltage", "current", "level")

    def __init__(self):
        self.voltage: float = 0.0
        self.current: float = 0.0
        self.level: int = 0

    def __str__(self) -> str:
        return (
            f"Battery:voltage={self.voltage},current={self.current},level={self.level}"
        )

    def __repr__(self) -> str:
        return (
            f"_BatteryCompat(voltage={self.voltage}, current={self.current}, "
            f"level={self.level})"
        )


class _GPSInfoCompat:
    """
    Compatibility wrapper to match dronekit.GPSInfo interface.

    Attributes:
        fix_type: GPS fix type (0-1: no fix, 2: 2d fix, 3: 3d fix)
        satellites_visible: Number of visible satellites
    """

    __slots__ = ("fix_type", "satellites_visible")

    def __init__(self):
        self.fix_type: int = 0
        self.satellites_visible: int = 0

    def __str__(self) -> str:
        return f"GPSInfo:fix={self.fix_type},num_sat={self.satellites_visible}"

    def __repr__(self) -> str:
        return (
            f"_GPSInfoCompat(fix_type={self.fix_type}, "
            f"satellites_visible={self.satellites_visible})"
        )


class _AttitudeCompat:
    """
    Compatibility wrapper to match dronekit.Attitude interface.

    All angles in radians.

    Attributes:
        pitch: Pitch angle in radians
        roll: Roll angle in radians
        yaw: Yaw angle in radians
    """

    __slots__ = ("pitch", "roll", "yaw")

    def __init__(self):
        self.pitch: float = 0.0
        self.roll: float = 0.0
        self.yaw: float = 0.0

    def __str__(self) -> str:
        return f"Attitude:pitch={self.pitch},yaw={self.yaw},roll={self.roll}"

    def __repr__(self) -> str:
        return f"_AttitudeCompat(pitch={self.pitch}, roll={self.roll}, yaw={self.yaw})"


class _VersionCompat:
    """
    Compatibility wrapper to match dronekit.Version interface.

    Attributes:
        major: Major version number
        minor: Minor version number
        patch: Patch version number
        release: Release type (if available)
    """

    __slots__ = ("major", "minor", "patch", "release")

    def __init__(self):
        self.major: int | None = None
        self.minor: int | None = None
        self.patch: int | None = None
        self.release: str | None = None

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self) -> str:
        return (
            f"_VersionCompat(major={self.major}, minor={self.minor}, "
            f"patch={self.patch})"
        )
