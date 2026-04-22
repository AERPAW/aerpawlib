"""
Vehicle implementations for the v1 API.

This package exposes shared and concrete vehicle classes used by v1 mission
scripts and runtime internals.

Capabilities:
- Re-export shared `Vehicle` infrastructure and `DummyVehicle` shim.
- Re-export concrete `Drone` and `Rover` implementations.

Usage:
- Import from `aerpawlib.v1.vehicles` when direct access to implementation
  modules is needed.
"""

from .core_vehicle import Vehicle, DummyVehicle
from .drone import Drone
from .rover import Rover

__all__ = ["Vehicle", "DummyVehicle", "Drone", "Rover"]
