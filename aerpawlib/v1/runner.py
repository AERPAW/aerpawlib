"""
Runner framework for AERPAW v1 experiments.

Use this module to build runnable experiment classes:
- ``BasicRunner`` for a single mission coroutine.
- ``StateMachine`` for explicit state transitions.
- ``ZmqStateMachine`` for externally coordinated, multi-vehicle state flows.

Typical authoring pattern:
1. Subclass one of the runner classes.
2. Decorate mission methods with ``@entrypoint`` or ``@state`` decorators.
3. Execute the script via the CLI with ``--api-version v1``.

Example run command:
``aerpawlib --api-version v1 --script my_mission.py --vehicle drone --conn udpin://127.0.0.1:14550``

See ``docs/CLI.md`` and ``docs/TUTORIALS.md`` for full script and runtime
workflows.
"""

from .runner_decorators import (
    at_init,
    background,
    entrypoint,
    expose_field_zmq,
    expose_zmq,
    state,
    timed_state,
)
from .runner_impl import (
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
