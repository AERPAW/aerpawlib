"""
.. include:: ../../../docs/v1/vehicles.md
"""

from .core_vehicle import Vehicle, DummyVehicle
from .drone import Drone
from .rover import Rover

__all__ = ["Vehicle", "DummyVehicle", "Drone", "Rover"]
