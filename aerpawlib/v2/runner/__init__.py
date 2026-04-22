"""
Runner framework for AERPAW v2 experiments.

This package provides the configuration models, decorators, and concrete
implementations used to define and execute v2 experiment scripts.

Typical authoring flow:
1. Subclass ``BasicRunner`` or ``StateMachine``.
2. Mark methods with ``@entrypoint`` or state decorators.
3. Run with the CLI using ``--api-version v2``.

Example run command:
``aerpawlib --api-version v2 --script my_mission.py --vehicle drone --conn udpin://127.0.0.1:14550``

For full command-line and walkthrough guidance, see ``docs/CLI.md``
"""

from __future__ import annotations

from .config import (
    BasicRunnerConfig,
    StateMachineConfig,
    StateSpec,
    ZmqStateMachineConfig,
)
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
)
