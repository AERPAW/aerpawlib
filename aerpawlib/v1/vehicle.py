"""
Vehicle facade module for the v1 API.

This module re-exports the concrete v1 vehicle types and compatibility classes
so scripts can import the full vehicle surface from one place.

Capabilities
- Re-export shared `Vehicle` and `DummyVehicle` types.
- Re-export concrete `Drone` and `Rover` implementations.
- Re-export telemetry compatibility wrappers used by legacy call sites.

Usage:
- Import vehicle types from `aerpawlib.v1` or `aerpawlib.v1.vehicle` in mission
  scripts and integration code.
"""

# Re-export from split files
from aerpawlib.v1.vehicles.core_vehicle import (
    Vehicle,
    DummyVehicle,
    _BatteryCompat,
    _GPSInfoCompat,
    _AttitudeCompat,
    _VersionCompat,
)
from aerpawlib.v1.vehicles.drone import Drone
from aerpawlib.v1.vehicles.rover import Rover

__all__ = [
    "Vehicle",
    "DummyVehicle",
    "Drone",
    "Rover",
    "_BatteryCompat",
    "_GPSInfoCompat",
    "_AttitudeCompat",
    "_VersionCompat",
]
