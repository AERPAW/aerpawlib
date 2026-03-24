"""
Runner for aerpawlib v2.

Supports config dataclass (explicit) or decorators (@entrypoint, @state, etc.).
"""

from __future__ import annotations

from .runner_config import (
    BasicRunnerConfig,
    StateMachineConfig,
    StateSpec,
    ZmqStateMachineConfig,
    V,
)
from .runner_decorators import (
    _AtInitDescriptor,
    _BackgroundDescriptor,
    _EntrypointDescriptor,
    _ExposeFieldZmqDescriptor,
    _ExposeZmqDescriptor,
    _StateDescriptor,
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
)

__all__ = [
    "V",
    "StateSpec",
    "BasicRunnerConfig",
    "StateMachineConfig",
    "ZmqStateMachineConfig",
    "Runner",
    "BasicRunner",
    "StateMachine",
    "ZmqStateMachine",
    "entrypoint",
    "state",
    "timed_state",
    "background",
    "at_init",
    "expose_zmq",
    "expose_field_zmq",
]
