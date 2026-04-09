"""
AERPAW v1 API.

The v1 API preserves the original aerpawlib mission programming model while
using MAVSDK-backed internals. This package re-exports the primary public v1
surface (vehicles, runner/state-machine decorators, utilities, and safety
helpers) so scripts can import from one namespace.

Create an experiment:
1. Subclass ``BasicRunner`` (single flow) or ``StateMachine`` (FSM flow).
2. Mark entry methods with ``@entrypoint`` or ``@state``/``@timed_state``.
3. Use vehicle operations like ``await vehicle.takeoff(...)`` and
   ``await vehicle.goto_coordinates(...)`` in your runner methods.

Run an experiment from the CLI:
``aerpawlib --api-version v1 --script my_mission.py --vehicle drone --conn udpin://127.0.0.1:14550``

See also:
- ``docs/CLI.md`` for CLI flags and config-file workflows.
- ``docs/TUTORIALS.md`` for end-to-end walkthroughs.
- ``docs/USER_GUIDE.md`` for operational guidance.
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
