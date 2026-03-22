"""
Structured event logging for aerpawlib v2.

Emits machine-readable JSON Lines for post-mission analysis and dashboards.
Structured logging is file-based only; omit --structured-log to disable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TextIO

from .log import LogComponent, get_logger

_logger = get_logger(LogComponent.ROOT)


class StructuredEventLogger:
    """Logs mission events as JSON Lines for machine-readable output.

    Events are written to a file only. Use with --structured-log FILE when
    running v2 experiments. Omit to disable file logging.
    Each event is also emitted at DEBUG severity (without timestamp) for
    console visibility when log level is DEBUG.
    """

    def __init__(self, output: TextIO) -> None:
        """Initialise the event logger.

        Args:
            output: File-like object to write JSON lines to. Required; use
                --structured-log FILE to enable.
        """
        self._output: TextIO = output
        self._closed = False

    def log_event(self, event_type: str, **kwargs: Any) -> None:
        """Log an event as a JSON line.

        Args:
            event_type: Event name (e.g. 'takeoff', 'location', 'land_complete').
            **kwargs: Additional event-specific fields (lat, lon, alt, etc.).
        """
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
        except (IOError, OSError):
            pass
        # Print event at DEBUG (without timestamp)
        without_ts = {k: v for k, v in record.items() if k != "timestamp"}
        _logger.log(logging.DEBUG, "event: %s", json.dumps(without_ts))

    def close(self) -> None:
        """Close the logger and release resources."""
        if not self._closed:
            self._closed = True
            try:
                self._output.close()
            except (IOError, OSError):
                pass
