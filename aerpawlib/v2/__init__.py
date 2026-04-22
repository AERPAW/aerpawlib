"""
AERPAW v2 API.

The v2 API is the async-first interface for aerpawlib, with single-loop
telemetry/command handling, modern runner descriptors, and integrated safety
checks. Import public v2 symbols directly from this package for mission
scripts.

Create an experiment:
1. Subclass ``BasicRunner`` or ``StateMachine`` from ``aerpawlib.v2.runner``.
2. Decorate runner methods with ``@entrypoint`` or state decorators.
3. Implement async mission steps with v2 vehicle methods (for example,
   ``await vehicle.goto_coordinates(...)`` and velocity/offboard helpers).

Run an experiment from the CLI:
``aerpawlib --api-version v2 --script my_mission.py --vehicle drone --conn udpin://127.0.0.1:14550``

See also:
- ``docs/CLI.md`` for command reference and config merging.
- ``docs/USER_GUIDE.md`` for mission execution workflows.
"""

from .constants import *
from .aerpaw import *
from .exceptions import *
from .external import *
from .geofence import *
from .plan import *
from .protocols import *
from .runner import *
from .testing import *
from .safety import *
from .types import *
from .vehicle import *
from .zmqutil import *
