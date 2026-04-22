"""Descriptor-based decorators for v2 runners (@entrypoint, @state, etc.)."""

from __future__ import annotations

import types
from enum import Enum, auto
from typing import Any, Callable, Optional, cast

from ..exceptions import (
    InvalidStateNameError,
    MultipleInitialStatesError,
    RunnerError,
)
from .config import (
    BasicRunnerConfig,
    StateSpec,
    ZmqStateMachineConfig,
    _ensure_state_machine_config,
)


class _EntrypointDescriptor:
    """Descriptor for @entrypoint. Uses __set_name__ to register."""

    def __init__(self, func: Callable) -> None:
        self.func = func
        self.name: Optional[str] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        if "config" in owner.__dict__ and isinstance(owner.config, BasicRunnerConfig):
            if owner.config.entrypoint != name:
                raise RunnerError(
                    f"Only one @entrypoint is allowed per runner class. "
                    f"Already registered '{owner.config.entrypoint}', "
                    f"cannot also register '{name}'."
                )
            return
        owner.config = BasicRunnerConfig(entrypoint=name)

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        if self.func is None:
            raise RuntimeError("Expose-field decorator not applied to function")
        func = cast(Callable, self.func)
        return types.MethodType(func, obj)


def entrypoint(func: Callable) -> _EntrypointDescriptor:
    """Mark a method as the BasicRunner entry point.

    Exactly one method per runner class may be decorated with this.

    Args:
        func: The async method to use as the entry point.

    Returns:
        An _EntrypointDescriptor that registers the method on the class.
    """
    return _EntrypointDescriptor(func)


class _StateType(Enum):
    """Internal state execution mode for state-machine methods."""

    STANDARD = auto()
    TIMED = auto()


class _StateDescriptor:
    """Descriptor for @state and @timed_state."""

    def __init__(
        self,
        name: str,
        first: bool = False,
        state_type: _StateType = _StateType.STANDARD,
        duration: float = 0.0,
        loop: bool = False,
    ) -> None:
        if not name:
            raise InvalidStateNameError()
        self.name = name
        self.first = first
        self.state_type = state_type
        self.duration = duration
        self.loop = loop
        self.func: Optional[Callable] = None

    def __call__(self, func: Callable) -> "_StateDescriptor":
        self.func = func
        return self

    def __set_name__(self, owner: type, attr_name: str) -> None:
        cfg = _ensure_state_machine_config(owner)
        if self.first:
            if cfg.initial_state:
                raise MultipleInitialStatesError()
            cfg.initial_state = self.name
        cfg.states.append(
            StateSpec(
                name=self.name,
                method_name=attr_name,
                first=self.first,
                duration=self.duration,
                loop=self.loop,
            )
        )

        zmq_name = getattr(self.func, "zmq_name", None)
        if zmq_name is not None:
            zmq_cfg = _ensure_state_machine_config(owner, require_zmq=True)
            if isinstance(zmq_cfg, ZmqStateMachineConfig):
                zmq_cfg.exposed_states[cast(str, zmq_name)] = cast(str, self.name)

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        if self.func is None:
            raise RuntimeError("State decorator not applied to function")
        if hasattr(self.func, "__get__"):
            return self.func.__get__(obj, objtype)
        return types.MethodType(self.func, obj)


def state(name: str, first: bool = False) -> Callable[[Callable], _StateDescriptor]:
    """Decorate a method as a named StateMachine state.

    Args:
        name: Unique state name used for transitions.
        first: If True, this state is the initial state of the machine.

    Returns:
        Decorator that registers the method as the named state.
    """

    def decorator(func: Callable) -> _StateDescriptor:
        if isinstance(func, _StateDescriptor):
            raise RunnerError(
                "A method cannot be decorated with more than one of @state/@timed_state"
            )
        desc = _StateDescriptor(name, first=first, state_type=_StateType.STANDARD)
        desc.func = func
        return desc

    return decorator


def timed_state(
    name: str,
    duration: float,
    loop: bool = False,
    first: bool = False,
) -> Callable[[Callable], _StateDescriptor]:
    """Decorate a method as a timed StateMachine state.

    The decorated method is called and then the runner waits for ``duration``
    seconds before advancing to the next state.  If ``loop`` is True the method
    is called repeatedly until the duration expires.

    Args:
        name: Unique state name used for transitions.
        duration: How long to remain in this state (seconds).
        loop: If True, re-invoke the method every state-machine tick within
            the duration window.
        first: If True, this state is the initial state of the machine.

    Returns:
        Decorator that registers the method as the named timed state.
    """

    def decorator(func: Callable) -> _StateDescriptor:
        if isinstance(func, _StateDescriptor):
            raise RunnerError(
                "A method cannot be decorated with more than one of @state/@timed_state"
            )
        desc = _StateDescriptor(
            name,
            first=first,
            state_type=_StateType.TIMED,
            duration=duration,
            loop=loop,
        )
        desc.func = func
        return desc

    return decorator


class _BackgroundDescriptor:
    """Descriptor for @background."""

    def __init__(self, func: Callable) -> None:
        self.func = func
        self.name: Optional[str] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        cfg = _ensure_state_machine_config(owner)
        cfg.backgrounds.append(name)

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        return types.MethodType(cast(Callable, self.func), obj)


def background(func: Callable) -> _BackgroundDescriptor:
    """Mark a method to run as a background task throughout the state machine.

    The decorated coroutine is started before the first state and runs
    concurrently until the runner finishes.

    Args:
        func: Async method to run as a background task.

    Returns:
        A _BackgroundDescriptor that registers the method on the class.
    """
    return _BackgroundDescriptor(func)


class _AtInitDescriptor:
    """Descriptor for @at_init."""

    def __init__(self, func: Callable) -> None:
        self.func = func
        self.name: Optional[str] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        cfg = _ensure_state_machine_config(owner)
        cfg.at_init.append(name)

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        return types.MethodType(cast(Callable, self.func), obj)


def at_init(func: Callable) -> _AtInitDescriptor:
    """Mark a method to run once at initialisation, before arming.

    Args:
        func: Async method to call during the init phase.

    Returns:
        An _AtInitDescriptor that registers the method on the class.
    """
    return _AtInitDescriptor(func)


class _ExposeZmqDescriptor:
    """Marker for @expose_zmq. Wraps @state descriptor to register it as ZMQ-exposed."""

    def __init__(self, zmq_name: str, wrapped: Any) -> None:
        if not zmq_name:
            raise InvalidStateNameError()
        self.zmq_name = zmq_name
        self.wrapped = wrapped

    def __set_name__(self, owner: type, attr_name: str) -> None:
        if hasattr(self.wrapped, "__set_name__"):
            self.wrapped.__set_name__(owner, attr_name)

        cfg = _ensure_state_machine_config(owner, require_zmq=True)
        if not isinstance(cfg, ZmqStateMachineConfig):
            raise RunnerError("Failed to initialize ZMQ state machine configuration")

        state_name = None
        for spec in cfg.states:
            if spec.method_name == attr_name:
                state_name = spec.name
                break
        if state_name is None:
            raise RunnerError(
                "@expose_zmq can only be used on @state/@timed_state methods"
            )
        cfg.exposed_states[self.zmq_name] = state_name

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        if hasattr(self.wrapped, "__get__"):
            return self.wrapped.__get__(obj, objtype)
        return types.MethodType(self.wrapped, obj)


def expose_zmq(name: str) -> Callable[[Any], _ExposeZmqDescriptor]:
    """Expose a state for remote ZMQ transition commands.

    Args:
        name: ZMQ message name that triggers a transition to this state.

    Returns:
        Decorator that wraps a ``@state`` descriptor and registers the ZMQ name.
    """

    def decorator(target: Any) -> _ExposeZmqDescriptor:
        return _ExposeZmqDescriptor(name, target)

    return decorator


class _ExposeFieldZmqDescriptor:
    """Marker for @expose_field_zmq. Just sets attributes on a method."""

    def __init__(self, zmq_name: str) -> None:
        if not zmq_name:
            raise InvalidStateNameError()
        self.zmq_name = zmq_name
        self.func: Optional[Callable] = None

    def __set_name__(self, owner: type, name: str) -> None:
        cfg = _ensure_state_machine_config(owner, require_zmq=True)
        if isinstance(cfg, ZmqStateMachineConfig):
            cfg.exposed_fields[cast(str, self.zmq_name)] = cast(str, name)

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        if obj is None:
            return self
        func = self.func
        if func is None:
            raise RuntimeError("Expose-field decorator not applied to function")
        return types.MethodType(cast(Callable, func), obj)

    def __call__(self, func: Callable) -> "_ExposeFieldZmqDescriptor":
        self.func = func
        return self


def expose_field_zmq(name: str) -> Callable[[Callable], _ExposeFieldZmqDescriptor]:
    """Expose a field method for ZMQ query from another runner.

    Args:
        name: ZMQ field name that remote runners use in query_field calls.

    Returns:
        Decorator that registers the method as a queryable ZMQ field.
    """

    def decorator(func: Callable) -> _ExposeFieldZmqDescriptor:
        desc = _ExposeFieldZmqDescriptor(name)
        desc.func = func
        return desc

    return decorator
