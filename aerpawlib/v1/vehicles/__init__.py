"""
Vehicle implementations for AERPAW v1.

The package re-exports the common ``Vehicle`` base type together with
``Drone`` and ``Rover`` concrete implementations.
"""

from .core_vehicle import Vehicle, DummyVehicle
from .drone import Drone
from .rover import Rover

__all__ = ["Vehicle", "DummyVehicle", "Drone", "Rover"]
