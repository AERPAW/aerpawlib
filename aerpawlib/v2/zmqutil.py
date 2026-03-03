"""
ZMQ utilities for aerpawlib v2.

Reuses logic from v1.
"""

import socket

from .constants import ZMQ_PROXY_OUT_PORT
from .log import LogComponent, get_logger

logger = get_logger(LogComponent.ZMQ)


def check_zmq_proxy_reachable(proxy_addr: str, timeout_s: float = 2.0) -> bool:
    """
    Check if ZMQ proxy is reachable before starting a runner.

    Returns:
        True if proxy port accepts connections.
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
    Start ZMQ forwarder (XSUB/XPUB proxy). Blocking.

    Start proxy before runners that use ZMQ bindings.
    """
    import zmq

    from .constants import ZMQ_PROXY_IN_PORT

    ctx = zmq.Context()
    p_sub = ctx.socket(zmq.XSUB)
    p_pub = ctx.socket(zmq.XPUB)
    p_sub.bind(f"tcp://*:{ZMQ_PROXY_IN_PORT}")
    p_pub.bind(f"tcp://*:{ZMQ_PROXY_OUT_PORT}")
    logger.info("ZMQ proxy started")
    zmq.proxy(p_sub, p_pub)
