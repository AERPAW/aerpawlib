"""
ZMQ utilities for aerpawlib v2.

Reuses logic from v1.
"""

import socket

import zmq

from .constants import (
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_REACHABILITY_TIMEOUT_S,
)
from .log import LogComponent, get_logger

logger = get_logger(LogComponent.ZMQ)


def check_zmq_proxy_reachable(
    proxy_addr: str, timeout_s: float = ZMQ_REACHABILITY_TIMEOUT_S
) -> bool:
    """Check if the ZMQ proxy is reachable before starting a runner.

    Args:
        proxy_addr: Hostname or IP address of the ZMQ proxy.
        timeout_s: Connection attempt timeout in seconds.

    Returns:
        True if the proxy port accepts TCP connections within the timeout.
    """
    try:
        with socket.create_connection(
            (proxy_addr, int(ZMQ_PROXY_OUT_PORT)), timeout=timeout_s
        ) as _:
            return True
    except (socket.error, OSError, ValueError):
        return False


def run_zmq_proxy() -> None:
    """Start a ZMQ XSUB/XPUB forwarder proxy. Blocking.

    Start this proxy in a separate process before launching any runners that
    use ZMQ bindings (ZmqStateMachine).
    """
    ctx = zmq.Context()
    p_sub = ctx.socket(zmq.XSUB)
    p_pub = ctx.socket(zmq.XPUB)
    p_sub.bind(f"tcp://*:{ZMQ_PROXY_IN_PORT}")
    p_pub.bind(f"tcp://*:{ZMQ_PROXY_OUT_PORT}")
    logger.info("ZMQ proxy started")
    zmq.proxy(p_sub, p_pub)
