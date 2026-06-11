"""
.. include:: ../../../docs/v2/vehicle.md
"""

from .base import DummyVehicle, Vehicle
from .drone import Drone
from .rover import Rover
from .task import VehicleTask

__all__ = ["Drone", "DummyVehicle", "Rover", "Vehicle", "VehicleTask"]
