"""State machine and BasicRunner configuration dataclasses for v2 runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, TypeVar

V = TypeVar("V")


def _is_zmq_state_machine_subclass(cls: type) -> bool:
    """True if cls is ZmqStateMachine or a subclass thereof."""
    return any(c.__name__ == "ZmqStateMachine" for c in cls.mro())


@dataclass
class StateSpec:
    """State metadata for StateMachineConfig."""

    name: str
    method_name: str
    first: bool = False
    duration: float = 0.0
    loop: bool = False


@dataclass
class BasicRunnerConfig:
    """Config for BasicRunner. Set explicitly or via @entrypoint."""

    entrypoint: str


@dataclass
class StateMachineConfig:
    """Config for StateMachine. Set explicitly or via @state, @timed_state, etc."""

    initial_state: str
    states: List[StateSpec] = field(default_factory=list)
    backgrounds: List[str] = field(default_factory=list)
    at_init: List[str] = field(default_factory=list)


@dataclass
class ZmqStateMachineConfig(StateMachineConfig):
    """Config for ZmqStateMachine. Adds exposed_states and exposed_fields."""

    exposed_states: Dict[str, str] = field(
        default_factory=dict
    )  # zmq_name -> state_name
    exposed_fields: Dict[str, str] = field(
        default_factory=dict
    )  # zmq_name -> method_name


def _nearest_parent_state_machine_config(owner: type) -> Optional[StateMachineConfig]:
    """Return closest inherited StateMachineConfig, if any."""
    for base in owner.__mro__[1:]:
        if "config" in base.__dict__ and isinstance(
            base.__dict__["config"], StateMachineConfig
        ):
            return base.__dict__["config"]
    return None


def _ensure_state_machine_config(
    owner: type, require_zmq: bool = False
) -> StateMachineConfig:
    """Ensure owner has an isolated config copy; optionally upgrade to ZMQ config."""
    cfg = owner.__dict__.get("config")
    if isinstance(cfg, ZmqStateMachineConfig):
        return cfg

    needs_zmq = require_zmq or _is_zmq_state_machine_subclass(owner)
    if isinstance(cfg, StateMachineConfig):
        parent_cfg = cfg
    else:
        parent_cfg = _nearest_parent_state_machine_config(owner)

    if needs_zmq:
        owner.config = ZmqStateMachineConfig(
            initial_state=parent_cfg.initial_state if parent_cfg else "",
            states=list(parent_cfg.states) if parent_cfg else [],
            backgrounds=list(parent_cfg.backgrounds) if parent_cfg else [],
            at_init=list(parent_cfg.at_init) if parent_cfg else [],
            exposed_states=dict(getattr(parent_cfg, "exposed_states", {})),
            exposed_fields=dict(getattr(parent_cfg, "exposed_fields", {})),
        )
    else:
        owner.config = StateMachineConfig(
            initial_state=parent_cfg.initial_state if parent_cfg else "",
            states=list(parent_cfg.states) if parent_cfg else [],
            backgrounds=list(parent_cfg.backgrounds) if parent_cfg else [],
            at_init=list(parent_cfg.at_init) if parent_cfg else [],
        )
    return owner.config
