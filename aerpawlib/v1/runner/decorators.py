"""Utilities and decorators used to build v1 runners.

This module provides the decorator primitives and small internal types that
``StateMachine`` / ``ZmqStateMachine`` and ``BasicRunner`` rely on.  The
decorators annotate user-defined methods with marker attributes that the
runner construction logic inspects (for example, ``StateMachine._build()``).

Overview of decorators and what they add
--------------------------------------
- ``@entrypoint``
  - Marks a single async entry function for ``BasicRunner``.
  - Adds ``_entrypoint = True`` to the function object.

- ``@state(name, first=False)``
  - Marks a standard state method for a ``StateMachine``.
  - Required attributes added: ``_is_state``, ``_state_name`` (str),
    ``_state_first`` (bool), ``_state_type`` set to ``_StateType.STANDARD``.
  - Raises ``InvalidStateNameError`` for empty names and ``StateMachineError``
    if a method is decorated as more than one state.

- ``@timed_state(name, duration, loop=False, first=False)``
  - Marks a timed state which will run for at least ``duration`` seconds.
  - Adds the same state markers as ``@state`` plus ``_state_type`` set to
    ``_StateType.TIMED``, ``_state_duration`` (float), and ``_state_loop`` (bool).
  - Timed states are executed in a small background task that repeatedly
    invokes the wrapped function if ``loop`` is True; the runner sleeps for
    ``duration`` seconds before allowing the state to finish.

- ``@expose_zmq(name)`` / ``@expose_field_zmq(name)``
  - Mark methods to be exposed over the ZMQ control/query API used by
    ``ZmqStateMachine``. These set ``_is_exposed_zmq`` /
    ``_is_exposed_field_zmq`` and ``_zmq_name``.

- ``@background``
  - Marks an async method to be executed repeatedly in the background while a
    ``StateMachine`` is running. Sets ``_is_background = True``.

- ``@at_init``
  - Marks an async function to run once during vehicle initialization before
    the vehicle is armed. Sets ``_run_at_init = True``.

Internal types and semantics
---------------------------
- ``_StateType``: enum used to distinguish normal and timed states.
- ``_State``: internal wrapper that knows how to execute a state function.
  For timed states, ``_State.run`` starts a background task that repeatedly
  calls the wrapped function (if ``loop`` is True) and then waits for the
  minimum duration (using ``aerpawlib.v1.constants.STATE_MACHINE_DELAY_S``
  between loop iterations). The last returned value from the wrapped
  function is used as the next state's name.

Usage notes and expectations
---------------------------
- Decorated functions are expected to be ``async`` coroutines; the runners
  will ``await`` them.
- State functions should return the next state's name (``str``) or ``None``
  to finish the state machine.
- Decorating a function with more than one state decorator will raise
  ``StateMachineError``.

Example
-------
    @state("start", first=True)
    async def start(self, vehicle):
        await vehicle.takeoff(5)
        return "patrol"

    @timed_state("patrol", duration=10, loop=True)
    async def patrol(self, vehicle):
        # called repeatedly while the timed state is active
        return None

"""

from __future__ import annotations

import asyncio
from enum import Enum, auto
from typing import Any, Callable, Optional, TypeVar

from aerpawlib.v1.constants import STATE_MACHINE_DELAY_S
from aerpawlib.v1.exceptions import (
    InvalidStateNameError,
    StateMachineError,
)
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


