"""
Logging utilities for aerpawlib.

Uses Python's standard logging with a colored console formatter.
Shared by v1 and tests.

@author: Julian Reder (quantumbagel)
"""

from __future__ import annotations

import logging
import sys
import time
from enum import Enum
from typing import Optional, Union


class LogLevel(Enum):
    """Log level enumeration matching Python logging."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    @classmethod
    def from_string(cls, level: str) -> "LogLevel":
        """Convert string to LogLevel."""
        level_upper = level.upper()
        if level_upper == "WARN":
            level_upper = "WARNING"
        return cls[level_upper]


class LogComponent(Enum):
    """Predefined logging components for categorized logging."""

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


class ColoredFormatter(logging.Formatter):
    """Colored console formatter matching aerpawlib's standard format."""

    COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        use_colors: bool = True,
    ):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "") if self.use_colors else ""
        reset = self.RESET if self.use_colors else ""
        bold = self.BOLD if self.use_colors else ""

        name = record.name
        if name.startswith("aerpawlib.v1."):
            name = "v1." + name[13:]
        elif name == "aerpawlib.v1":
            name = "v1"
        elif name.startswith("aerpawlib."):
            name = name[10:]  # "aerpawlib.sitl" -> "sitl"

        timestamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        level_letter = record.levelname[0]

        if record.levelno >= logging.WARNING:
            prefix = f"{color}{bold}[{name} {level_letter}]{reset}"
        else:
            prefix = f"{color}[{name}]{reset}"

        if record.levelno == logging.DEBUG:
            return f"{prefix} {color}{timestamp}{reset} {record.getMessage()}"
        else:
            return f"{prefix} {record.getMessage()}"


# Global state
_configured = False
_default_format = "[%(name)s] %(message)s"


def configure_logging(
    level: Union[LogLevel, str, int] = LogLevel.INFO,
    format_str: Optional[str] = None,
    use_colors: bool = True,
    log_file: Optional[str] = None,
    root_name: str = "aerpawlib.v1",
) -> None:
    """
    Configure logging for aerpawlib.

    Args:
        level: Log level (LogLevel enum, string, or int)
        format_str: Custom format string (uses default if None)
        use_colors: Use colored output for console
        log_file: Optional path to log file
        root_name: Logger name to configure (default: aerpawlib.v1).
            Use "aerpawlib" to configure the whole package (e.g. for tests).
    """
    global _configured

    if isinstance(level, LogLevel):
        level_value = level.value
    elif isinstance(level, str):
        level_value = LogLevel.from_string(level).value
    else:
        level_value = level

    fmt = format_str or _default_format
    root_logger = logging.getLogger(root_name)
    root_logger.setLevel(level_value)
    root_logger.handlers.clear()
    root_logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level_value)
    console.setFormatter(ColoredFormatter(fmt, use_colors=use_colors))
    root_logger.addHandler(console)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level_value)
        file_handler.setFormatter(logging.Formatter(fmt))
        root_logger.addHandler(file_handler)

    _configured = True


def get_logger(
    component: Union[LogComponent, str] = LogComponent.ROOT,
) -> logging.Logger:
    """
    Get a logger for the specified component.

    Args:
        component: LogComponent enum value or string logger name.

    Returns:
        A configured logging.Logger instance.
    """
    name = (
        component.value if isinstance(component, LogComponent) else component
    )
    return logging.getLogger(name)


def set_level(
    level: Union[LogLevel, str, int],
    component: Optional[LogComponent] = None,
) -> None:
    """Set the log level for a component or the v1 root logger."""
    if isinstance(level, LogLevel):
        level_value = level.value
    elif isinstance(level, str):
        level_value = LogLevel.from_string(level).value
    else:
        level_value = level

    logger_name = component.value if component else "aerpawlib.v1"
    logging.getLogger(logger_name).setLevel(level_value)


__all__ = [
    "LogLevel",
    "LogComponent",
    "ColoredFormatter",
    "configure_logging",
    "get_logger",
    "set_level",
]
