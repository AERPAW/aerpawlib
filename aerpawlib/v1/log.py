"""
.. include:: ../../docs/v1/log.md
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from aerpawlib.log import (
    ColoredFormatter,
    LogLevel,
)
from aerpawlib.log import (
    LogComponent as LogComponentBase,
)
from aerpawlib.log import (
    configure_logging as _configure_logging,
)
from aerpawlib.log import (
    get_logger as _get_logger,
)
from aerpawlib.log import (
    set_level as _set_level,
)

if TYPE_CHECKING:
    import logging


class LogComponent(LogComponentBase, str, Enum):
    """Predefined logging components for v1 (categorized loggers)."""

    ROOT = "aerpawlib.v1"
    VEHICLE = "aerpawlib.v1.vehicle"
    DRONE = "aerpawlib.v1.vehicle.drone"
    ROVER = "aerpawlib.v1.vehicle.rover"
    SAFETY = "aerpawlib.v1.safety"
    RUNNER = "aerpawlib.v1.runner"
    TELEMETRY = "aerpawlib.v1.telemetry"
    COMMAND = "aerpawlib.v1.command"
    NAVIGATION = "aerpawlib.v1.navigation"
    CONNECTION = "aerpawlib.v1.connection"
    GEOFENCE = "aerpawlib.v1.geofence"
    ZMQ = "aerpawlib.v1.zmq"
    AERPAW = "aerpawlib.v1.aerpaw"
    OEO = "aerpawlib.v1.oeo"
    EXTERNAL = "aerpawlib.v1.external"
    USER = "aerpawlib.v1.user"
    SITL = "aerpawlib.sitl"


def get_logger(
    component: LogComponent | str = LogComponent.ROOT,
) -> logging.Logger:
    """Return a logger for the given v1 component name."""
    return _get_logger(component)


def configure_logging(
    level: LogLevel | str | int = LogLevel.INFO,
    format_str: str | None = None,
    use_colors: bool = True,
    log_file: str | None = None,
    root_name: str = "aerpawlib.v1",
) -> None:
    """Configure logging with the v1 root logger (``aerpawlib.v1``) by default."""
    _configure_logging(
        level=level,
        format_str=format_str,
        use_colors=use_colors,
        log_file=log_file,
        root_name=root_name,
    )


def set_level(
    level: LogLevel | str | int,
    component: LogComponent | str | None = None,
) -> None:
    """Set the log level for a v1 component or the v1 root logger."""
    if component is None:
        _set_level(level, LogComponent.ROOT)
    else:
        _set_level(level, component)


__all__ = [
    "LogComponent",
    "LogLevel",
    "ColoredFormatter",
    "configure_logging",
    "get_logger",
    "set_level",
]
