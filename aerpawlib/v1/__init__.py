"""
Public entrypoint for the AERPAW v1 API.

This package re-exports the primary v1 symbols so mission scripts can import
vehicles, runners, safety helpers, and utilities from one namespace.

Capabilities:
- Re-export core runner types (`Runner`, `BasicRunner`, `StateMachine`).
- Re-export vehicle types (`Drone`, `Rover`, `Vehicle`).
- Re-export safety, utility, and compatibility helpers.

Usage:
- Import from `aerpawlib.v1` in mission scripts to keep imports stable.

Notes:
- v1 preserves the historical dual-loop model (background MAVSDK loop plus
  main runner loop). New greenfield code can prefer v2, while v1 remains
  supported for existing scripts.
"""

from .external import *
from .aerpaw import *
from .zmqutil import *
from .safety import *
from .util import *
from .vehicle import *
from .runner import *
from .constants import *
from .exceptions import *
