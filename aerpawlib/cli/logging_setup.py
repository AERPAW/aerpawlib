"""CLI logging configuration for aerpawlib."""

import logging
import sys
from typing import Optional

from aerpawlib.cli.constants import (
    AERPAWLIB_LOGGER_NAME,
    CYGRPC_LOGGER_NAME,
    GRPC_CYGRPC_LOGGER_NAME,
    LOG_FORMAT_STRING,
    LOG_DATETIME_FORMAT,
    LOG_FILE_OPEN_MODE,
)
from aerpawlib.log import ColoredFormatter


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure logging for aerpawlib and user scripts.

    Configures the root logger so that logs from all modules (aerpawlib,
    user scripts, and libraries) are captured and formatted consistently.

    Args:
        verbose: Enable debug (DEBUG level) logging
        quiet: Suppress most output (WARNING level only)
        log_file: Optional path to write logs to file

    Returns:
        Configured logger instance
    """
    root_logger = logging.getLogger()

    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    root_logger.setLevel(level)

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter(use_colors=True))
    root_logger.addHandler(console_handler)

    logging.getLogger(CYGRPC_LOGGER_NAME).setLevel(logging.WARNING)
    logging.getLogger(GRPC_CYGRPC_LOGGER_NAME).setLevel(logging.WARNING)

    if log_file:
        file_handler = logging.FileHandler(log_file, mode=LOG_FILE_OPEN_MODE)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            LOG_FORMAT_STRING,
            datefmt=LOG_DATETIME_FORMAT,
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    return logging.getLogger(AERPAWLIB_LOGGER_NAME)
