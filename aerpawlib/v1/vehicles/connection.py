"""MAVSDK connection string parsing and validation (v1)."""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from aerpawlib.v1.exceptions import AerpawConnectionError

_MAVSDK_VALID_SCHEMES = frozenset(
    ("udpin", "udpout", "tcpin", "tcpout", "serial", "tcp", "udp")
)


def _parse_udp_connection_port(connection_string: str) -> Optional[Tuple[str, int]]:
    """
    Parse host and port from a UDP connection string for port-in-use checks.

    Supports MAVSDK/aerpawlib UDP formats:
    - udp://:port, udp://host:port
    - udpin://:port, udpin://host:port, udpin://[ipv6]:port
    - udpout:// returns None (client mode; no local bind)

    Returns:
        (host, port) for server/listen modes, None for client mode or non-UDP.
    """
    parsed = urlparse(connection_string.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc

    if scheme == "udpout":
        return None

    if scheme not in ("udp", "udpin"):
        return None

    if not netloc:
        return None

    ipv6_match = re.match(r"\[([^\]]+)\]:(\d+)$", netloc)
    if ipv6_match:
        host, port_str = ipv6_match.group(1), ipv6_match.group(2)
    else:
        parts = netloc.rsplit(":", 1)
        if len(parts) != 2:
            return None
        host, port_str = parts

    try:
        port = int(port_str)
    except ValueError:
        return None

    if not (0 < port <= 65535):
        return None

    host = host.strip() if host else "0.0.0.0"
    return (host, port)


def _validate_connection_string(conn_str: str) -> None:
    """Raise AerpawConnectionError immediately if conn_str is malformed.

    This prevents spawning mavsdk_server with an invalid URL, which would
    otherwise cause a silent 30-second hang before ConnectionTimeoutError.
    """
    s = conn_str.strip()
    if "://" not in s:
        raise AerpawConnectionError(
            f"Invalid connection string {conn_str!r}: missing '://'. "
            "Expected format e.g. 'udpin://0.0.0.0:14550', "
            "'udpout://host:port', 'tcpin://host:port', "
            "'tcpout://host:port', or 'serial:///dev/path[:baud]'."
        )
    scheme = s.split("://")[0].lower()
    if scheme not in _MAVSDK_VALID_SCHEMES:
        raise AerpawConnectionError(
            f"Invalid connection string {conn_str!r}: unknown scheme {scheme!r}. "
            f"Supported schemes: {', '.join(sorted(_MAVSDK_VALID_SCHEMES))}."
        )
