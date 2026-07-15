"""
Implementation of ZMQ utilities for v2.
"""

import pickle
import socket

import zmq
from zmq.utils.monitor import recv_monitor_message

from .constants import (
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_REACHABILITY_TIMEOUT_S,
)
from .log import LogComponent, get_logger

logger = get_logger(LogComponent.ZMQ)


def check_zmq_proxy_reachable(
    proxy_addr: str,
    timeout_s: float = ZMQ_REACHABILITY_TIMEOUT_S,
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
            (proxy_addr, int(ZMQ_PROXY_OUT_PORT)),
            timeout=timeout_s,
        ) as _:
            return True
    except (OSError, ValueError):
        return False


def _log_connection_event(channel_name: str, evt: dict) -> None:
    event_id = evt["event"]
    endpoint = evt["endpoint"]
    if isinstance(endpoint, bytes):
        endpoint = endpoint.decode("utf-8", errors="ignore")

    if event_id == zmq.EVENT_ACCEPTED:
        logger.info(f"[Connection] Peer connected to {channel_name} (endpoint: {endpoint})")
    elif event_id == zmq.EVENT_DISCONNECTED:
        logger.info(f"[Connection] Peer disconnected from {channel_name} (endpoint: {endpoint})")


def _log_message_flow(direction: str, msg_parts: list[bytes]) -> None:
    parsed_msg = None
    for part in msg_parts:
        try:
            obj = pickle.loads(part)
            if isinstance(obj, dict):
                parsed_msg = obj
                break
        except Exception:
            pass

    if parsed_msg:
        msg_type = parsed_msg.get("msg_type")
        sender = parsed_msg.get("from")
        recipient = parsed_msg.get("identifier")

        if msg_type == "TRANSITION":
            next_state = parsed_msg.get("next_state")
            logger.info(f"[Message] {direction}: TRANSITION message from='{sender}', to='{recipient}', next_state='{next_state}'")
        elif msg_type == "FIELD_REQUEST":
            field = parsed_msg.get("field")
            logger.info(f"[Message] {direction}: FIELD_REQUEST message from='{sender}', to='{recipient}', field='{field}'")
        elif msg_type == "FIELD_CALLBACK":
            field = parsed_msg.get("field")
            value = parsed_msg.get("value")
            logger.info(f"[Message] {direction}: FIELD_CALLBACK message from='{sender}', to='{recipient}', field='{field}', value={value}")
        else:
            logger.info(f"[Message] {direction}: Custom dict payload: {parsed_msg}")
    else:
        raw_reprs = [part[:50].hex() + ("..." if len(part) > 50 else "") for part in msg_parts]
        logger.info(f"[Message] {direction}: Raw frames (hex): {raw_reprs}")


def _log_subscription_flow(msg_parts: list[bytes]) -> None:
    for part in msg_parts:
        if len(part) > 0:
            action = part[0]
            topic = part[1:]
            action_name = "SUBSCRIBE" if action == 1 else "UNSUBSCRIBE" if action == 0 else f"UNKNOWN_ACTION({action})"
            topic_str = topic.decode("utf-8", errors="ignore")
            logger.info(f"[Subscription] Received: {action_name} for topic: '{topic_str}'")


def run_zmq_proxy(
    in_port: int | str = ZMQ_PROXY_IN_PORT,
    out_port: int | str = ZMQ_PROXY_OUT_PORT,
) -> None:
    """Start a ZMQ XSUB/XPUB forwarder proxy with connection and message logging. Blocking.

    Start this proxy in a separate process before launching any runners that
    use ZMQ bindings (ZmqStateMachine).
    """
    ctx = zmq.Context()
    p_sub = ctx.socket(zmq.XSUB)
    p_pub = ctx.socket(zmq.XPUB)

    # Set up monitors before bind to ensure we don't miss early events
    monitor_sub = p_sub.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)
    monitor_pub = p_pub.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)

    p_sub.bind(f"tcp://*:{in_port}")
    p_pub.bind(f"tcp://*:{out_port}")

    logger.info(f"ZMQ proxy started. Listening for incoming on port {in_port} and outgoing on port {out_port}")

    poller = zmq.Poller()
    poller.register(p_sub, zmq.POLLIN)
    poller.register(p_pub, zmq.POLLIN)
    poller.register(monitor_sub, zmq.POLLIN)
    poller.register(monitor_pub, zmq.POLLIN)

    try:
        while True:
            events = dict(poller.poll())

            if monitor_sub in events:
                evt = recv_monitor_message(monitor_sub)
                _log_connection_event("XSUB (publisher channel)", evt)

            if monitor_pub in events:
                evt = recv_monitor_message(monitor_pub)
                _log_connection_event("XPUB (subscriber channel)", evt)

            if p_sub in events:
                msg_parts = p_sub.recv_multipart()
                _log_message_flow("Received", msg_parts)
                p_pub.send_multipart(msg_parts)
                _log_message_flow("Forwarded", msg_parts)

            if p_pub in events:
                msg_parts = p_pub.recv_multipart()
                _log_subscription_flow(msg_parts)
                p_sub.send_multipart(msg_parts)

    except KeyboardInterrupt:
        logger.info("ZMQ proxy stopped by user")
    finally:
        poller.unregister(p_sub)
        poller.unregister(p_pub)
        poller.unregister(monitor_sub)
        poller.unregister(monitor_pub)
        monitor_sub.close()
        monitor_pub.close()
        p_sub.close()
        p_pub.close()
        ctx.term()
