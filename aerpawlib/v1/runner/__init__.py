"""
.. include:: ../../../docs/v1/runner.md
"""

import asyncio

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

in_background = asyncio.ensure_future
"""Alias for asyncio.ensure_future to make it more intuitive to use"""
sleep = asyncio.sleep
"""Alias for asyncio.sleep"""

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
