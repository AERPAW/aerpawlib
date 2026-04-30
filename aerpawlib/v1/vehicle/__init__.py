"""
.. include:: ../../../docs/v1/vehicle.md
"""

from .core_vehicle import Vehicle
from .drone import Drone
from .dummy_vehicle import DummyVehicle
from .rover import Rover

__all__ = ["Vehicle", "DummyVehicle", "Drone", "Rover"]
