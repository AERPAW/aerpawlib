"""Shared MAVSDK connection string validation and UDP port parsing."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def parse_udp_connection_port(connection_string: str) -> tuple[str, int] | None:
    """Parse host and port from a UDP listen connection string.

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
