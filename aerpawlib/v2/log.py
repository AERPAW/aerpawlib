"""
.. include:: ../../docs/v2/log.md
"""

from __future__ import annotations

import logging
from typing import Optional, Union

from aerpawlib.log import (
    LogComponent as LogComponentBase,
    LogLevel,
    configure_logging as _configure_logging,
    get_logger as _get_logger,
    set_level as _set_level,
)


class LogComponent(LogComponentBase):
    """v2 logging component names (dotted logger keys)."""

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
    return _get_logger(component)


def configure_logging(
    level: Union[LogLevel, str, int] = LogLevel.INFO,
    format_str: Optional[str] = None,
    use_colors: bool = True,
    log_file: Optional[str] = None,
    root_name: str = "aerpawlib.v2",
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
    _set_level(level, component or LogComponent.ROOT)


__all__ = [
    "LogComponent",
    "get_logger",
    "configure_logging",
    "set_level",
    "LogLevel",
]
