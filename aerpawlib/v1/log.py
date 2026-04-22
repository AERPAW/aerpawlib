"""
Legacy logging re-exports for v1 scripts.

This module preserves the historical `aerpawlib.v1.log` import path by
re-exporting selected logging symbols from `aerpawlib.log`.

Capabilities:
- Re-export logger configuration and retrieval helpers.
- Keep older v1 imports working without code changes.

Notes:
- New code should prefer importing directly from `aerpawlib.log`.
"""

from aerpawlib.log import (
    ColoredFormatter,
    LogComponent,
    LogLevel,
    configure_logging,
    get_logger,
    set_level,
)

__all__ = [
    "LogLevel",
    "LogComponent",
    "ColoredFormatter",
    "configure_logging",
    "get_logger",
    "set_level",
]
