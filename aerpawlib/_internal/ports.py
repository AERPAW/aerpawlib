"""Local TCP/UDP port availability helpers shared by v1 and v2."""

from __future__ import annotations

import errno
import socket


def is_udp_port_in_use(host: str, port: int) -> bool:
    """Return True if a UDP bind on ``host:port`` fails because the port is taken."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def is_tcp_port_in_use(host: str, port: int) -> bool:
    """Return True if a TCP bind on ``host:port`` fails with EADDRINUSE."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                return True
            raise
