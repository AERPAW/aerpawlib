"""
Utilities and decorators used to build v1 runners.

This module provides the decorator primitives and small internal types that
``StateMachine`` / ``ZmqStateMachine`` and ``BasicRunner`` rely on.  The
decorators annotate user-defined methods with marker attributes that the
runner construction logic inspects (for example, ``StateMachine._build()``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, TypeVar

from aerpawlib.v1.constants import STATE_MACHINE_DELAY_S
from aerpawlib.v1.exceptions import (
    InvalidStateNameError,
    StateMachineError,
)

if TYPE_CHECKING:
    from aerpawlib.v1.vehicle import Vehicle

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

    async def run(self, runner: Any, vehicle: Vehicle) -> str | None:
        """
        Run the function associated with this state.

        Args:
            runner: The Runner instance executing this state.
            vehicle: The Vehicle instance to be controlled.

        Returns:
            str: The name of the next state to transition to.
        """
        if getattr(self._func, "_state_type", None) == _StateType.STANDARD:
            # this is cursed
            return await self._func.__func__(runner, vehicle)
        if getattr(self._func, "_state_type", None) == _StateType.TIMED:
            running = True

            async def _bg() -> str | None:
                """Run a timed state until duration elapses or loop exits."""
                nonlocal running
                last_state: str | None = None
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
            return await r
        return None


def entrypoint(func: _DecoratedFunc) -> _DecoratedFunc:
    """Mark the single async entry point for a BasicRunner.

    Args:
        func: Async method invoked with the connected vehicle.

    Returns:
        The decorated function with an entrypoint marker.
    """
    func._entrypoint = True
    return func


def state(
    name: str,
    first: bool = False,
) -> Callable[[_DecoratedFunc], _DecoratedFunc]:
    """Decorate a method as a named StateMachine state.

    Args:
        name: Unique state name used for transitions.
        first: If True, this state is the initial state.

    Returns:
        Decorator that registers the method as the named state.

    Raises:
        InvalidStateNameError: If name is empty.
    """
    if name == "":
        raise InvalidStateNameError()

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        """Mark a method as a standard state."""
        if hasattr(func, "_is_state"):
            raise StateMachineError(
                "A method cannot be decorated with more than one of @state/@timed_state",
            )
        func._is_state = True
        func._state_name = name
        func._state_first = first
        func._state_type = _StateType.STANDARD
        return func

    return decorator


def timed_state(
    name: str,
    duration: float,
    loop: bool = False,
    first: bool = False,
) -> Callable[[_DecoratedFunc], _DecoratedFunc]:
    """Decorate a method as a timed StateMachine state.

    Args:
        name: Unique state name used for transitions.
        duration: Minimum seconds to remain in this state.
        loop: If True, re-invoke the method until duration elapses.
        first: If True, this state is the initial state.

    Returns:
        Decorator that registers the method as the named timed state.

    Raises:
        InvalidStateNameError: If name is empty.
    """
    if name == "":
        raise InvalidStateNameError()

    def decorator(func: _DecoratedFunc) -> _DecoratedFunc:
        """Mark a method as a timed state."""
        if hasattr(func, "_is_state"):
            raise StateMachineError(
                "A method cannot be decorated with more than one of @state/@timed_state",
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
    """Expose a state for remote ZMQ transition commands.

    Args:
        name: ZMQ message name that triggers a transition to this state.

    Returns:
        Decorator that marks the state method as ZMQ-exposed.

    Raises:
        InvalidStateNameError: If name is empty.
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
    """Expose a method return value for ZMQ query_field calls.

    Args:
        name: ZMQ field name remote runners use in query_field.

    Returns:
        Decorator that marks the method as a queryable ZMQ field.

    Raises:
        InvalidStateNameError: If name is empty.
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
    """Mark a method to run concurrently while the StateMachine is active.

    Args:
        func: Async method restarted on exception until the runner finishes.

    Returns:
        The decorated function with a background marker.
    """
    func._is_background = True
    return func


def at_init(func: _DecoratedFunc) -> _DecoratedFunc:
    """Mark a method to run once before arming and the first state.

    Args:
        func: Async setup method called during initialization.

    Returns:
        The decorated function with an at_init marker.
    """
    func._run_at_init = True
    return func
