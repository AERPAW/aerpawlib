"""
Logging for aerpawlib v2 API.

Wraps aerpawlib.log with v2-specific component names.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

from aerpawlib.log import (
    LogLevel,
    configure_logging as _configure_logging,
    get_logger as _get_logger,
)


class LogComponent:
    """v2 logging components."""

    ROOT = "aerpawlib.v2"
    VEHICLE = "aerpawlib.v2.vehicle"
    DRONE = "aerpawlib.v2.vehicle.drone"
    ROVER = "aerpawlib.v2.vehicle.rover"
    SAFETY = "aerpawlib.v2.safety"
    RUNNER = "aerpawlib.v2.runner"
    AERPAW = "aerpawlib.v2.aerpaw"
    ZMQ = "aerpawlib.v2.zmq"


def get_logger(
    component: Union[object, str] = LogComponent.ROOT,
) -> logging.Logger:
    """Return a logger for the specified v2 component.

    Args:
        component: A LogComponent constant or a dotted logger name string.

    Returns:
        A standard Python logger configured for the given component.
    """
    name = _component_name(component)
    return _get_logger(name)


def _component_name(component: Union[object, str]) -> str:
    if isinstance(component, str):
        return component
    value = getattr(component, "value", None)
    if isinstance(value, str):
        return value
    raise TypeError(
        "component must be a logger name string or an enum with a string 'value'"
    )


def configure_logging(
    level: Union[LogLevel, str, int] = LogLevel.INFO,
    format_str: Optional[str] = None,
    use_colors: bool = True,
    log_file: Optional[str] = None,
    root_name: str = LogComponent.ROOT,
) -> None:
    """Configure logging for v2 modules.

    Defaults to `aerpawlib.v2` so v2 loggers get handlers without requiring
    callers to pass `root_name` manually.
    """
    _configure_logging(
        level=level,
        format_str=format_str,
        use_colors=use_colors,
        log_file=log_file,
        root_name=root_name,
    )


def set_level(
    level: Union[LogLevel, str, int],
    component: Optional[Union[object, str]] = None,
) -> None:
    """Set logging level for v2 root/component loggers."""
    if isinstance(level, LogLevel):
        level_value = level.value
    elif isinstance(level, str):
        level_value = LogLevel.from_string(level).value
    else:
        level_value = level

    target = _component_name(component or LogComponent.ROOT)
    logging.getLogger(target).setLevel(level_value)


__all__ = [
    "LogComponent",
    "get_logger",
    "configure_logging",
    "set_level",
    "LogLevel",
]
