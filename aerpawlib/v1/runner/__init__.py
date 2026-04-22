"""
High-level runner API for v1 experiments.

This module re-exports runner implementations and decorators used to build v1
missions with either a single-entry flow or a state-machine flow.

Capabilities:
- Re-export `Runner`, `BasicRunner`, `StateMachine`, and `ZmqStateMachine`.
- Re-export runner decorators (`@entrypoint`, `@state`, `@timed_state`, etc.).
- Provide a stable import surface for mission authoring.

Usage:
- Import runner symbols from `aerpawlib.v1.runner` or `aerpawlib.v1` when
  defining mission logic classes.
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