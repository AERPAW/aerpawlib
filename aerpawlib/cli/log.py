"""
.. include:: ../../docs/cli/log.md
"""

from __future__ import annotations

from aerpawlib.log import LogComponent as LogComponentBase


class LogComponent(LogComponentBase):
    """Dotted logger names for the aerpawlib command-line / entrypoint stack."""

    ROOT = "aerpawlib"
    CLI = "aerpawlib.cli"
    # JSON Lines mission events (``--structured-log``); used by
    # :mod:`aerpawlib.structured_log`.
    STRUCTURED = "aerpawlib.structured"


__all__ = ["LogComponent"]
