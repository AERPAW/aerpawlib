"""
Local TCP/UDP port availability helpers.

This module provides lightweight bind-based checks used by v1 startup logic to
detect likely local port conflicts before launching vehicle connections.

Capabilities
- Check UDP port availability on a target host/interface.
- Check TCP port availability on IPv4 or IPv6 hosts.

Notes:
- These are fast pre-checks intended to improve error messages before deeper
  MAVSDK connection setup begins.
"""

import errno
import socket


def is_udp_port_in_use(host: str, port: int) -> bool:
    """
    Check if a local UDP port is in use by trying to bind to it.

    Args:
        host: The local IP address to bind to (e.g., '127.0.0.1', '0.0.0.0', or '::1').
        port: The port number to check.

    Returns:
        True if the port is in use, False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def is_tcp_port_in_use(host: str, port: int) -> bool:
    """
    Check if a local TCP port is in use by trying to bind to it.

    Args:
        host: The local IP address to bind to (e.g., '127.0.0.1', '0.0.0.0').
        port: The port number to check.

    Returns:
        True if the port is in use, False otherwise.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                return True
            raise
