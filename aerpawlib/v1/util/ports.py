"""
Local TCP/UDP port availability helpers.

This module re-exports the shared implementation used by v1 startup logic
to detect likely local port conflicts before launching vehicle connections.
"""

from aerpawlib._internal.ports import is_tcp_port_in_use, is_udp_port_in_use

__all__ = ["is_tcp_port_in_use", "is_udp_port_in_use"]
