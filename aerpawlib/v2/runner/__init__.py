"""
Runner framework for AERPAW v2.

This package provides configuration models, runner decorators, and concrete
runner implementations for basic, state-machine, and ZMQ-enabled flows.
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
