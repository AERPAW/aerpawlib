"""
ZMQ proxy helpers for v1 runners.

This module provides low-level helpers to check and run the synchronous ZMQ
forwarder used by `ZmqStateMachine` flows.

Capabilities:
- Check whether the proxy publish endpoint is reachable over TCP.
- Run a blocking XSUB/XPUB proxy for inter-runner pub/sub traffic.

Usage:
- Start the proxy in a separate process or thread before launching ZMQ-enabled
  runner instances.

Notes:
- The v1 proxy implementation is synchronous by design.
"""

import socket
import zmq

from aerpawlib.log import get_logger, LogComponent
from .constants import (
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_PROXY_CHECK_TIMEOUT_S,
)

# Configure logger
logger = get_logger(LogComponent.ZMQ)


def check_zmq_proxy_reachable(
    proxy_addr: str, timeout_s: float = ZMQ_PROXY_CHECK_TIMEOUT_S
) -> bool:
    """
    Check if the ZMQ proxy is reachable before starting a runner.

    The ZMQ proxy must be started before any runners that use ZMQ bindings.
    This performs a quick TCP connectivity check to the proxy's subscribe port.

    Args:
        proxy_addr: Hostname or IP of the proxy server.
        timeout_s: Connection timeout in seconds.

    Returns:
        True if the proxy port is accepting connections, False otherwise.
    """
    try:
        with socket.create_connection(
            (proxy_addr, int(ZMQ_PROXY_OUT_PORT)), timeout=timeout_s
        ) as _:
            return True
    except (socket.error, OSError, ValueError):
        return False


def run_zmq_proxy() -> None:
    """
    Start a ZMQ forwarder device (XSUB/XPUB proxy).

    This proxy acts as a central hub for ZMQ-based communication between
    multiple runners. It binds to ZMQ_PROXY_IN_PORT for incoming messages
    and ZMQ_PROXY_OUT_PORT for outgoing broadcast.

    Important:
        Start the proxy before any runners that use ZMQ bindings. If ports
        5570/5571 are already in use, bind() will raise.

    Note:
        This function is blocking and currently uses synchronous ZMQ.
        It should be called in a separate process or thread.
    """
    # Asyncio ZMQ will not be supported by v1
    # This feature will be added to v2
    zmq_context = zmq.Context()

    p_sub = zmq_context.socket(zmq.XSUB)
    p_pub = zmq_context.socket(zmq.XPUB)

    p_sub.bind(f"tcp://*:{ZMQ_PROXY_IN_PORT}")
    p_pub.bind(f"tcp://*:{ZMQ_PROXY_OUT_PORT}")

    logger.info("launching zmq proxy")
    zmq.proxy(p_sub, p_pub)
