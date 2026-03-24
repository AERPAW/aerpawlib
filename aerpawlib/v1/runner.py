"""
Collection of execution frameworks that can be extended to make scripts
runnable using aerpawlib. The most basic framework is `Runner` -- any custom
frameworks *must* extend it to be executable.

This is the v1 API runner module, now using MAVSDK internally.

@author: Julian Reder (quantumbagel)
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
