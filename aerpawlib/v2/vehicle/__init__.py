"""
Vehicle module for aerpawlib v2.
"""

from .base import Vehicle, DummyVehicle
from .drone import Drone
from .rover import Rover

__all__ = ["Vehicle", "DummyVehicle", "Drone", "Rover"]
