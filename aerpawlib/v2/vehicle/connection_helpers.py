"""Connection string validation and async wait helpers for v2 vehicles."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from aerpawlib.v2.constants import (
    DEFAULT_MAV_UDP_PORT,
    MAX_POSITION_TOLERANCE_M,
    MIN_POSITION_TOLERANCE_M,
)
from aerpawlib.v2.exceptions import AerpawConnectionError
from aerpawlib.v2.log import LogComponent, get_logger

logger = get_logger(LogComponent.VEHICLE)

_MAVSDK_VALID_SCHEMES = frozenset(("udpin", "tcpin", "serial", "tcp", "udp"))


def _validate_connection_string(conn_str: str) -> None:
    """Raise AerpawConnectionError immediately if conn_str is malformed.

    Prevents spawning mavsdk_server with an invalid URL, which would otherwise
    cause a silent timeout hang instead of a fast, clear error.
    """
    s = conn_str.strip()
    if "://" not in s:
        raise AerpawConnectionError(
            f"Invalid connection string {conn_str!r}: missing '://'. "
            f"Expected format e.g. 'udpin://0.0.0.0:{DEFAULT_MAV_UDP_PORT}', "
            "'udpout://host:port', 'tcpin://host:port', "
            "'tcpout://host:port', or 'serial:///dev/path[:baud]'.",
        )
    scheme = s.split("://")[0].lower()
    if scheme not in _MAVSDK_VALID_SCHEMES:
        raise AerpawConnectionError(
            f"Invalid connection string {conn_str!r}: unknown scheme {scheme!r}. "
            f"Supported schemes: {', '.join(sorted(_MAVSDK_VALID_SCHEMES))}.",
        )


def _validate_tolerance(tolerance: float, param_name: str = "tolerance") -> float:
    """Validate that tolerance is within acceptable bounds.

    Args:
        tolerance: Tolerance value in metres to validate.
        param_name: Name of the parameter (used in error messages).

    Returns:
        The validated tolerance value (unchanged).

    Raises:
        ValueError: If tolerance is outside [MIN_POSITION_TOLERANCE_M,
            MAX_POSITION_TOLERANCE_M].
    """
    if not (MIN_POSITION_TOLERANCE_M <= tolerance <= MAX_POSITION_TOLERANCE_M):
        raise ValueError(
            f"{param_name} must be between {MIN_POSITION_TOLERANCE_M} and "
            f"{MAX_POSITION_TOLERANCE_M}, got {tolerance}",
        )
    return tolerance


async def _wait_for_condition(
    condition: Callable[[], bool],
    timeout: float | None = None,
    poll_interval: float = 0.05,
    timeout_message: str = "Operation timed out",
) -> bool:
    """Wait until a condition callable returns True.

    Args:
        condition: Zero-argument callable; returns True when the wait is over.
        timeout: Maximum seconds to wait. None means wait indefinitely.
        poll_interval: Seconds between condition checks; also yields the
            event loop between checks.
        timeout_message: Message used in the TimeoutError if the wait expires.

    Returns:
        True when the condition becomes True.

    Raises:
        TimeoutError: If timeout is reached before the condition is satisfied.
    """
    start = time.monotonic()
    while not condition():
        if timeout is not None and (time.monotonic() - start) > timeout:
            logger.warning(
                f"_wait_for_condition timeout after {timeout}s: {timeout_message}",
            )
            raise TimeoutError(timeout_message)
        await asyncio.sleep(poll_interval)
    return True
