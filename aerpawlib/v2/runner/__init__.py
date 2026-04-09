"""
Runner for aerpawlib v2.

Supports config dataclass (explicit) or decorators (@entrypoint, @state, etc.).
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
