"""CLI logging configuration for aerpawlib."""

from __future__ import annotations

import logging
import sys

from rich.logging import RichHandler
from rich.text import Text

from aerpawlib.cli.log import LogComponent
from aerpawlib.log import ColoredFormatter


class AnsiRichHandler(RichHandler):
    """Subclass of RichHandler that renders ANSI escape sequences in log messages."""

    def render_message(self, record: logging.LogRecord, message: str) -> Text:
        return Text.from_ansi(message)


def setup_logging(
    level: int = logging.INFO,
    log_file: str | None = None,
) -> logging.Logger:
    """
    Configure logging for aerpawlib and user scripts.

    Configures the root logger so that logs from all modules (aerpawlib,
    user scripts, and libraries) are captured and formatted consistently.

    Args:
        level: the logging level
        log_file: Optional path to write logs to file

    Returns:
        Configured logger instance
    """
    root_logger = logging.getLogger()

    root_logger.setLevel(level)

    root_logger.handlers.clear()

    if sys.stdout.isatty():
        from aerpawlib.cli.progress_bar import console

        console_handler = AnsiRichHandler(
            console=console,
            show_time=False,
            show_level=False,
            show_path=False,
        )
    else:
        console_handler = logging.StreamHandler(sys.stdout)

    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter(use_colors=True))
    root_logger.addHandler(console_handler)
    # Mute the gRPC logging. This is done because it is very spammy,
    # especially on debug and on macOS.
    logging.getLogger("_cython.cygrpc").setLevel(logging.WARNING)
    logging.getLogger("grpc._cython.cygrpc").setLevel(logging.WARNING)

    if log_file:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    return logging.getLogger(LogComponent.ROOT)
