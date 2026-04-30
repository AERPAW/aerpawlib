"""
Structured JSON Lines event logging for aerpawlib (v1 and v2).

File-based only; omit --structured-log to disable.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any, TextIO

from aerpawlib.cli.log import LogComponent
from aerpawlib.log import get_logger

_logger = get_logger(LogComponent.STRUCTURED)


class StructuredEventLogger:
    """Logs mission events as JSON Lines for machine-readable output.

    Events are written to a file only. Use with ``--structured-log FILE``.
    Each event is also emitted at DEBUG severity (without timestamp) for
    console visibility when log level is DEBUG.
    """

    def __init__(self, output: TextIO) -> None:
        self._output: TextIO = output
        self._closed = False

    def log_event(self, event_type: str, **kwargs: Any) -> None:
        """Log an event as a JSON line."""
        if self._closed:
            return
        record = {
            "timestamp": time.time(),
            "event": event_type,
            **kwargs,
        }
        line = json.dumps(record) + "\n"
        try:
            self._output.write(line)
            self._output.flush()
        except OSError:
            pass
        without_ts = {k: v for k, v in record.items() if k != "timestamp"}
        _logger.log(logging.DEBUG, "event: %s", json.dumps(without_ts))

    def close(self) -> None:
        """Close the logger and release resources."""
        if not self._closed:
            self._closed = True
            with contextlib.suppress(OSError):
                self._output.close()
