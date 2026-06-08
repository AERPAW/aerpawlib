"""
Connection string parsing and validation helpers for v1 vehicles.

This module validates and parses MAVSDK-style connection URLs so startup errors
can be surfaced early with clear messages.

Capabilities:
- Validate scheme/format for supported MAVSDK connection strings.
- Parse UDP bind host/port for local port-conflict checks.

Notes:
- Validation is intentionally early to avoid delayed failures during MAVSDK
  server initialization.
"""

from __future__ import annotations

from aerpawlib._internal.connection_string import (
    parse_udp_connection_port as _parse_udp_connection_port,  # noqa: F401
)
from aerpawlib._internal.connection_string import (
    validate_connection_scheme,
)
from aerpawlib.v1.exceptions import AerpawConnectionError


def _validate_connection_string(conn_str: str) -> None:
    """Raise AerpawConnectionError immediately if conn_str is malformed."""
    validate_connection_scheme(
        conn_str,
        raise_error=AerpawConnectionError,
        example_port=14550,
    )
