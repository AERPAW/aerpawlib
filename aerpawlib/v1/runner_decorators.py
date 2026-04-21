"""
Decorators and internal state machinery for v1 runners.

This module defines decorator primitives that annotate runner methods for
entrypoints, state transitions, timed states, background jobs, and ZMQ
exposure, plus the internal `_State` execution helper.

Capabilities
- Mark methods for discovery by `StateMachine._build()`.
- Describe timed/looping state behavior through decorator metadata.
- Mark methods/fields for ZMQ-driven control in `ZmqStateMachine`.

Notes:
- Decorators store marker attributes; scheduling behavior is implemented by
  runner classes during build and execution.
"""

from __future__ import annotations

import asyncio
from enum import Enum, auto
from typing import Any, Callable, Optional, TypeVar

from .constants import STATE_MACHINE_DELAY_S
from .exceptions import (
    InvalidStateNameError,
    StateMachineError,
)
from .vehicle import Vehicle

_Runnable = Callable[..., Any]
_DecoratedFunc = TypeVar("_DecoratedFunc", bound=Callable[..., Any])


class _StateType(Enum):
    """Internal enum describing how a state function executes."""

    STANDARD = auto()
    TIMED = auto()


class _State:
    """
    Internal representation of a state in a StateMachine.

    Attributes:
        _name: The name of the state.
        _func: The function to be executed for this state.
    """

    _name: str
    _func: _Runnable

    def __init__(self, func: _Runnable, name: str) -> None:
        self._name = name
        self._func = func

    async def run(self, runner: Any, vehicle: Vehicle) -> Optional[str]:
        """
        Run the function associated with this state.

        Args:
            runner: The Runner instance executing this state.
            vehicle: The Vehicle instance to be controlled.

        Returns:
            str: The name of the next state to transition to.
        """
        if self._func._state_type == _StateType.STANDARD:
            return await self._func.__func__(runner, vehicle)
        elif self._func._state_type == _StateType.TIMED:
            running = True

            async def _bg() -> Optional[str]:
                """Run a timed state until duration elapses or loop exits."""
                nonlocal running
                last_state: Optional[str] = None
                while running:
                    last_state = await self._func.__func__(runner, vehicle)
                    if not running:
                        break
                    if not self._func._state_loop:
                        running = False
                        break
                    await asyncio.sleep(STATE_MACHINE_DELAY_S)
                return last_state

            r = asyncio.ensure_future(_bg())
            await asyncio.sleep(self._func._state_duration)
            running = False
            next_state = await r
            return next_state
        return None


def entrypoint(func: _DecoratedFunc) -> _DecoratedFunc:
    """
    Decorator used to identify the entry point used by `BasicRunner` driven
    scripts.

    The function decorated by this is expected to be `async`
    """
    func._entrypoint = True
    return func


def state(name: str, first: bool = False) -> Callable[[_DecoratedFunc], _DecoratedFunc]:
    """
    Decorator to specify a state in a StateMachine.

    Args:
        name: The name of the state.
        first: Whether this is the initial state of the machine.
            Defaults to False.

    Returns:
        Callable: The decorated function.

    Raises:
        InvalidStateNameError: If the name is empty.
    """
    if name == "":
        raise InvalidStateNameError()

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        """Mark a method as a standard state."""
        if hasattr(func, "_is_state"):
            raise StateMachineError(
                "A method cannot be decorated with more than one of "
                "@state/@timed_state"
            )
        func._is_state = True
        func._state_name = name
        func._state_first = first
        func._state_type = _StateType.STANDARD
        return func

    return decorator


def timed_state(
    name: str, duration: float, loop: bool = False, first: bool = False
) -> Callable[[_DecoratedFunc], _DecoratedFunc]:
    """
    Decorator for a state that runs for a fixed duration.

    Args:
        name: The name of the state.
        duration: Minimum duration in seconds for this state.
        loop: Whether to repeatedly call the decorated function
            during the duration. Defaults to False.
        first: Whether this is the initial state. Defaults to False.

    Returns:
        Callable: The decorated function.

    Raises:
        InvalidStateNameError: If the name is empty.
    """
    if name == "":
        raise InvalidStateNameError()

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        """Mark a method as a timed state."""
        if hasattr(func, "_is_state"):
            raise StateMachineError(
                "A method cannot be decorated with more than one of "
                "@state/@timed_state"
            )
        func._is_state = True
        func._state_name = name
        func._state_first = first
        func._state_type = _StateType.TIMED
        func._state_duration = duration
        func._state_loop = loop
        return func

    return decorator


def expose_zmq(name: str) -> Callable[[_DecoratedFunc], _DecoratedFunc]:
    """
    Decorator to expose a state for remote control via ZMQ.

    Args:
        name: The name of the state to expose.

    Returns:
        Callable: The decorated function.

    Raises:
        InvalidStateNameError: If the name is empty.
    """
    if name == "":
        raise InvalidStateNameError()

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        """Mark a state method as exposed for remote ZMQ transitions."""
        func._is_exposed_zmq = True
        func._zmq_name = name
        return func

    return decorator


def expose_field_zmq(name: str) -> Callable[[_DecoratedFunc], _DecoratedFunc]:
    """
    Decorator to make a field requestable via ZMQ.

    Args:
        name: The name of the field to expose.

    Returns:
        Callable: The decorated function.

    Raises:
        InvalidStateNameError: If the name is empty.
    """
    if name == "":
        raise InvalidStateNameError()

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        """Mark a method as exposed for remote ZMQ field requests."""
        func._is_exposed_field_zmq = True
        func._zmq_name = name
        return func

    return decorator


def background(func: _DecoratedFunc) -> _DecoratedFunc:
    """
    Designate a function to be run in parallel to a StateMachine.

    Args:
        func: The asynchronous function to run in the background.

    Returns:
        Callable: The decorated function.
    """
    func._is_background = True
    return func


def at_init(func: _DecoratedFunc) -> _DecoratedFunc:
    """
    Designate a function to be run during vehicle initialization.

    The function will run before the vehicle is armed.

    Args:
        func: The asynchronous function to run.

    Returns:
        Callable: The decorated function.
    """
    func._run_at_init = True
    return func
