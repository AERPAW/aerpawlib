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
    "BasicRunner",
    "Runner",
    "StateMachine",
    "ZmqStateMachine",
    "at_init",
    "background",
    "entrypoint",
    "expose_field_zmq",
    "expose_zmq",
    "in_background",
    "sleep",
    "state",
    "timed_state",
]
