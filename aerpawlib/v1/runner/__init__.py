"""aerpawlib.v1.runner
======================

Runner API for v1 experiments.

This module re-exports runner implementations and decorators used to build v1
missions with either a single-entry flow (``BasicRunner``) or a state-machine
flow (``StateMachine`` / ``ZmqStateMachine``).

Key concepts
-------------
- BasicRunner: a simple runner with a single ``@entrypoint`` async function.
  Use this for straightforward scripts where you control flow explicitly.

- StateMachine: a richer runner that supports multiple named states via the
  ``@state`` and ``@timed_state`` decorators, plus background tasks via
  ``@background``. States are simple async functions that return the next
  state's name (or ``None`` to finish). The first state is marked with
  ``first=True`` on the decorator.

- ZmqStateMachine: extends ``StateMachine`` and exposes helpers for
  multi-vehicle coordination over ZMQ (querying fields, transitioning remote
  runners, and exposing fields via ``@expose_field_zmq`` / ``@expose_zmq``).

Decorators and helpers
----------------------
- ``@entrypoint``: marks a single-entry async function for ``BasicRunner``.
- ``@state(name, first=False)``: defines a state for ``StateMachine``.
- ``@timed_state(name, duration)``: runs a state for at least ``duration``
  seconds.
- ``@background``: runs a repeating background task (StateMachine only).
- ``@at_init``: run once during runner initialization.
- ``@expose_zmq`` / ``@expose_field_zmq``: expose RPC/field handlers for
  ZMQ-based runners.
- ``in_background`` and ``sleep``: convenience helpers used by runner
  implementations and user code.

Typical usage examples
----------------------
Basic runner example::

    from aerpawlib.v1.runner import BasicRunner, entrypoint
    from aerpawlib.v1 import Drone

    class MyScript(BasicRunner):
        @entrypoint
        async def run(self, vehicle: Drone):
            await vehicle.takeoff(5)
            await vehicle.land()

StateMachine snippet::

    from aerpawlib.v1.runner import StateMachine, state, timed_state, background

    class MySm(StateMachine):
        @state(name="start", first=True)
        async def start(self, vehicle):
            await vehicle.takeoff(5)
            return "patrol"

        @timed_state(name="patrol", duration=10)
        async def patrol(self, vehicle):
            # run for at least 10 seconds
            return "land"

Notes
-----
Decorators typically set marker attributes that ``StateMachine._build()``
inspects when constructing the runtime state graph. ``ZmqStateMachine`` is the
convenience path for multi-vehicle experiments and exposes helpers for
transitioning remote runners and querying remote fields.

"""

from .decorators import (
    at_init,
    background,
    entrypoint,
    expose_field_zmq,
    expose_zmq,
    state,
    timed_state,
)
from .impl import (
    BasicRunner,
    Runner,
    StateMachine,
    ZmqStateMachine,
    in_background,
    sleep,
)

__all__ = [
    "Runner",
    "BasicRunner",
    "StateMachine",
    "ZmqStateMachine",
    "entrypoint",
    "state",
    "timed_state",
    "expose_zmq",
    "expose_field_zmq",
    "background",
    "at_init",
    "in_background",
    "sleep",
]