"""
.. include:: ../docs/log.md
"""

from __future__ import annotations

import datetime
import logging
import sys
from enum import Enum
from typing import Any


class LogLevel(Enum):
    """Log level enumeration matching Python logging."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    @classmethod
    def from_string(cls, level: str) -> LogLevel:
        """Convert string to LogLevel."""
        level_upper = level.upper()
        if level_upper == "WARN":
            level_upper = "WARNING"
        return cls[level_upper]


class LogComponent:
    """Base for categorized logger names.

    Concrete component sets live in :mod:`aerpawlib.v1.log`,
    :mod:`aerpawlib.v2.log`, and :mod:`aerpawlib.cli.log`. Do not add members
    here.
    """

    __slots__ = ()


def _component_name(component: object) -> str:
    """Resolve a logger name from a string, enum, or namespace with string values."""
    if isinstance(component, str):
        return component
    if isinstance(component, Enum):
        return str(component.value)
    value = getattr(component, "value", None)
    if isinstance(value, str):
        return value
    raise TypeError(
        "component must be a logger name string, an enum member, or an object "
        "with a string 'value'",
    )


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
        fmt: str | None = None,
        datefmt: str | None = None,
        use_colors: bool = True,
    ):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "") if self.use_colors else ""
        reset = self.RESET if self.use_colors else ""
        bold = self.BOLD if self.use_colors else ""

        name = record.name
        if name == "root":
            name = "aerpawlib"
        elif name.startswith("aerpawlib."):
            name = name[10:]  # "aerpawlib.v1.vehicle" -> "v1.vehicle"
        elif "." in name:
            # User scripts: show last two parts for context
            # e.g. "examples.v1.basic_runner" -> "v1.basic_runner"
            parts = name.split(".")
            name = ".".join(parts[-2:]) if len(parts) >= 2 else parts[-1]

        timestamp = datetime.datetime.fromtimestamp(record.created).strftime(
            "%H:%M:%S.%f",
        )
        level_letter = record.levelname[0]

        if record.levelno >= logging.WARNING:
            prefix = f"{color}{bold}[{name} {level_letter}]{reset}"
        else:
            prefix = f"{color}[{name}]{reset}"

        timestamp_display = (
            f"{color}{timestamp}{reset}" if self.use_colors else timestamp
        )
        return f"{prefix} {timestamp_display} {record.getMessage()}"


# Global state
_configured = False
_default_format = "[%(name)s] %(message)s"


def configure_logging(
    level: LogLevel | str | int = LogLevel.INFO,
    format_str: str | None = None,
    use_colors: bool = True,
    log_file: str | None = None,
    root_name: str = "aerpawlib",
) -> None:
    """
    Configure logging for aerpawlib.

    Args:
        level: Log level (LogLevel enum, string, or int)
        format_str: Custom format string (uses default if None)
        use_colors: Use colored output for console
        log_file: Optional path to log file
        root_name: Logger name to configure (default: ``aerpawlib``).
            Use :func:`aerpawlib.v1.log.configure_logging` or
            :func:`aerpawlib.v2.log.configure_logging` for versioned roots.
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


def get_logger(component: Any = "aerpawlib") -> logging.Logger:
    """
    Get a logger for the specified component.

    Args:
        component: Dotted logger name string, or a :class:`LogComponent` /
            enum / object with a string ``value`` (see versioned log modules).

    Returns:
        A configured logging.Logger instance.
    """
    name = _component_name(component)
    return logging.getLogger(name)


def set_level(
    level: LogLevel | str | int,
    component: Any | None = None,
) -> None:
    """Set the log level for a component or the package root logger."""
    if isinstance(level, LogLevel):
        level_value = level.value
    elif isinstance(level, str):
        level_value = LogLevel.from_string(level).value
    else:
        level_value = level

    logger_name = "aerpawlib" if component is None else _component_name(component)
    logging.getLogger(logger_name).setLevel(level_value)


__all__ = [
    "LogLevel",
    "LogComponent",
    "ColoredFormatter",
    "configure_logging",
    "get_logger",
    "set_level",
]
