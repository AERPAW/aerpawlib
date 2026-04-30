"""
Vehicle state for aerpawlib v2.

Plain attributes updated by telemetry (no ThreadSafeValue).
"""

from __future__ import annotations

import math
import time

from aerpawlib.v2.constants import EKF_READY_FLAGS
from aerpawlib.v2.types import Attitude, Battery, Coordinate, GPSInfo, VectorNED


class VehicleState:
    """Mutable telemetry state updated by MAVSDK subscription callbacks.

    All attributes are updated in-place on the single asyncio event loop;
    no locking is required.
    """

    def __init__(self) -> None:
        # Position
        self._position_lat: float = 0.0
        self._position_lon: float = 0.0
        self._position_alt: float = 0.0
        self._position_abs_alt: float = 0.0
        # Velocity
        self._velocity_ned: VectorNED = VectorNED(0, 0, 0)
        # Attitude / heading
        self._attitude: Attitude = Attitude(0.0, 0.0, 0.0)
        self._heading_deg: float = 0.0
        # Battery
        self._battery: Battery = Battery(0.0, 0.0, 0)
        # GPS
        self._gps: GPSInfo = GPSInfo(0, 0)
        # Home
        self._home: Coordinate | None = None
        self._home_abs_alt: float = 0.0
        # Armed / mode
        self._armed: bool = False
        self._armable: bool = False
        self._mode: str = "UNKNOWN"
        self._last_arm_time: float = 0.0
        self._armed_telemetry_received: bool = False
        self._prearm_checks_ok: bool = False
        self._ekf_ready: bool = False

    @property
    def ekf_ready(self) -> bool:
        """Return True if EKF reports ready for takeoff (ArduPilot)."""
        return self._ekf_ready

    @property
    def position(self) -> Coordinate:
        """Return the current position as a Coordinate (relative altitude)."""
        return Coordinate(self._position_lat, self._position_lon, self._position_alt)

    @property
    def home_coords(self) -> Coordinate | None:
        """Return the home coordinate, or None if not yet received."""
        return self._home

    @property
    def home_amsl(self) -> float:
        """Return the home position altitude above mean sea level (AMSL) in metres."""
        return self._home_abs_alt

    @property
    def velocity(self) -> VectorNED:
        """Return the current velocity as a NED vector (m/s)."""
        return self._velocity_ned

    @property
    def heading(self) -> float:
        """Return the current heading in degrees, normalised to [0, 360)."""
        return self._heading_deg % 360

    @property
    def attitude(self) -> Attitude:
        """Return the current attitude (roll, pitch, yaw in radians)."""
        return self._attitude

    @property
    def battery(self) -> Battery:
        """Return the latest battery telemetry."""
        return self._battery

    @property
    def gps(self) -> GPSInfo:
        """Return the latest GPS telemetry."""
        return self._gps

    @property
    def armed(self) -> bool:
        """Return True if the vehicle is currently armed."""
        return self._armed

    @property
    def armable(self) -> bool:
        """Return True if the vehicle reports it can be armed."""
        return self._armable

    @property
    def mode(self) -> str:
        """Return the current flight mode name (e.g. 'GUIDED', 'OFFBOARD')."""
        return self._mode

    @property
    def last_arm_time(self) -> float:
        """Return the monotonic timestamp of the last arm event (0.0 if never armed)."""
        return self._last_arm_time

    def update_position(
        self, lat: float, lon: float, rel_alt: float, abs_alt: float,
    ) -> None:
        """Update position from a telemetry message.

        Args:
            lat: Latitude in degrees.
            lon: Longitude in degrees.
            rel_alt: Relative altitude in metres (above home).
            abs_alt: Absolute altitude (AMSL) in metres.
        """
        self._position_lat = lat
        self._position_lon = lon
        self._position_alt = rel_alt
        self._position_abs_alt = abs_alt

    def update_attitude(self, roll: float, pitch: float, yaw: float) -> None:
        """Update attitude and derive heading from yaw.

        Args:
            roll: Roll angle in radians.
            pitch: Pitch angle in radians.
            yaw: Yaw angle in radians.
        """
        self._heading_deg = math.degrees(yaw) % 360
        self._attitude = Attitude(roll, pitch, yaw)

    def update_velocity(self, north: float, east: float, down: float) -> None:
        """Update the NED velocity vector.

        Args:
            north: North component in m/s.
            east: East component in m/s.
            down: Down component in m/s.
        """
        self._velocity_ned = VectorNED(north, east, down)

    def update_gps(self, fix_type: int, satellites: int) -> None:
        """Update GPS status.

        Args:
            fix_type: MAVSDK GPS fix type integer (0–3+).
            satellites: Number of satellites visible.
        """
        self._gps = GPSInfo(fix_type, satellites)

    def update_battery(self, voltage: float, current: float, level: int) -> None:
        """Update battery telemetry.

        Args:
            voltage: Battery voltage in volts.
            current: Battery current draw in amperes.
            level: Remaining charge as an integer percentage (0–100).
        """
        self._battery = Battery(voltage, current, level)

    def update_mode(self, mode: str) -> None:
        """Update the current flight mode name.

        Args:
            mode: Flight mode string as reported by MAVSDK (e.g. 'OFFBOARD').
        """
        self._mode = mode

    def update_armed(self, armed: bool) -> None:
        """Update the armed state and record arm timestamp on transition to armed.

        Args:
            armed: True if the vehicle is now armed.
        """
        old = self._armed
        self._armed = armed
        self._armed_telemetry_received = True
        if armed and not old:
            self._last_arm_time = time.monotonic()

    def update_armable(
        self,
        global_ok: bool,
        local_ok: bool,
        home_ok: bool,
        armable: bool,
    ) -> None:
        """Update the armable flag from health telemetry.

        The vehicle is considered armable only when all conditions are True.

        Args:
            global_ok: True if global position estimate is OK.
            local_ok: True if local position estimate is OK.
            home_ok: True if home position is set.
            armable: True if the vehicle's own health check passes.
        """
        # Armable when MAVSDK health reports OK. SYS_STATUS prearm check removed
        # (was ArduPilot-specific); EKF readiness is checked separately for takeoff.
        self._armable = global_ok and local_ok and home_ok and armable

    def update_prearm_bits(self, ok: bool) -> None:
        """Update the MAV_SYS_STATUS_PREARM_CHECK bit status.

        Args:
            ok: True if the bit is set.
        """
        self._prearm_checks_ok = ok

    def update_ekf_from_flags(self, flags: int) -> None:
        """Update EKF takeoff-readiness from EKF_STATUS_REPORT flags.

        Args:
            flags: Raw flags value from EKF_STATUS_REPORT MAVLink message.
        """
        self._ekf_ready = (flags & EKF_READY_FLAGS) == EKF_READY_FLAGS

    def update_home(
        self, lat: float, lon: float, rel_alt: float, abs_alt: float,
    ) -> None:
        """Update the home position.

        Args:
            lat: Home latitude in degrees.
            lon: Home longitude in degrees.
            rel_alt: Home relative altitude in metres (typically 0).
            abs_alt: Home absolute altitude (AMSL) in metres.
        """
        self._home_abs_alt = abs_alt
        self._home = Coordinate(lat, lon, rel_alt)
