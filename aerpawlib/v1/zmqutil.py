"""
ZMQ proxy reachability check and runner for v1.
"""

import pickle
import socket

import zmq
from zmq.utils.monitor import recv_monitor_message

from aerpawlib.v1.log import LogComponent, get_logger

from .constants import (
    ZMQ_PROXY_CHECK_TIMEOUT_S,
    ZMQ_PROXY_IN_PORT,
    ZMQ_PROXY_OUT_PORT,
    ZMQ_TYPE_FIELD_CALLBACK,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_GOODBYE,
    ZMQ_TYPE_HELLO,
    ZMQ_TYPE_TRANSITION,
)

# Configure logger
logger = get_logger(LogComponent.ZMQ)

# Legacy msg_type strings used in older tests and scripts.
_LEGACY_MSG_TYPES = {
    "TRANSITION": ZMQ_TYPE_TRANSITION,
    "FIELD_REQUEST": ZMQ_TYPE_FIELD_REQUEST,
    "FIELD_CALLBACK": ZMQ_TYPE_FIELD_CALLBACK,
}


def check_zmq_proxy_reachable(
    proxy_addr: str,
    timeout_s: float = ZMQ_PROXY_CHECK_TIMEOUT_S,
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
            (proxy_addr, int(ZMQ_PROXY_OUT_PORT)),
            timeout=timeout_s,
        ) as _:
            return True
    except (OSError, ValueError):
        return False


def _normalize_msg_type(msg_type: object) -> str | None:
    if not isinstance(msg_type, str):
        return None
    return _LEGACY_MSG_TYPES.get(msg_type, msg_type)


def _format_runner_message(msg: dict) -> str:
    msg_type = _normalize_msg_type(msg.get("msg_type"))
    sender = msg.get("from", "?")
    recipient = msg.get("identifier", "?")

    if msg_type == ZMQ_TYPE_HELLO:
        return f"hello client connected: name={sender!r}"
    if msg_type == ZMQ_TYPE_GOODBYE:
        return f"goodbye client disconnected: name={sender!r}"
    if msg_type == ZMQ_TYPE_TRANSITION:
        next_state = msg.get("next_state", "?")
        return f"state_transition {sender} -> {recipient}: next_state={next_state!r}"
    if msg_type == ZMQ_TYPE_FIELD_REQUEST:
        field = msg.get("field", "?")
        return f"field_request {sender} -> {recipient}: field={field!r}"
    if msg_type == ZMQ_TYPE_FIELD_CALLBACK:
        field = msg.get("field", "?")
        value = msg.get("value")
        return f"field_callback {sender} -> {recipient}: field={field!r}, value={value!r}"
    return f"unrecognized runner message from={sender!r} to={recipient!r}: {msg}"


def _log_connection_event(channel: str, evt: dict) -> None:
    event_id = evt["event"]
    if event_id == zmq.EVENT_ACCEPTED:
        logger.info("Runner %s client connected", channel)
    elif event_id == zmq.EVENT_DISCONNECTED:
        logger.info("Runner %s client disconnected", channel)


def _log_forwarded_message(msg_parts: list[bytes]) -> None:
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
        logger.info("Forwarded %s", _format_runner_message(parsed_msg))
        return

    raw_reprs = [part[:50].hex() + ("..." if len(part) > 50 else "") for part in msg_parts]
    logger.warning("Forwarded non-runner payload (raw hex): %s", raw_reprs)


def _log_subscription_flow(msg_parts: list[bytes]) -> None:
    for part in msg_parts:
        if not part:
            continue
        action = part[0]
        topic = part[1:]
        topic_str = topic.decode("utf-8", errors="ignore")
        if action == 1:
            if topic_str:
                logger.debug("Runner subscribed to topic %r", topic_str)
            else:
                logger.debug("Runner subscribed to all topics")
        elif action == 0:
            if topic_str:
                logger.debug("Runner unsubscribed from topic %r", topic_str)
            else:
                logger.debug("Runner unsubscribed from all topics")
        else:
            logger.warning("Unknown subscription action %s for topic %r", action, topic_str)


def run_zmq_proxy(
    in_port: int | str = ZMQ_PROXY_IN_PORT,
    out_port: int | str = ZMQ_PROXY_OUT_PORT,
) -> None:
    """
    Start a ZMQ forwarder device (XSUB/XPUB proxy) with connection and message logging.

    This proxy acts as a central hub for ZMQ-based communication between
    multiple runners. It binds to ZMQ_PROXY_IN_PORT for incoming messages
    and ZMQ_PROXY_OUT_PORT for outgoing broadcast.

    Important:
        Start the proxy before any runners that use ZMQ bindings. If ports
        5570/5571 are already in use, bind() will raise.

    Note:
        This function is blocking. It should be called in a separate process or thread.
    """
    ctx = zmq.Context()
    p_sub = ctx.socket(zmq.XSUB)
    p_pub = ctx.socket(zmq.XPUB)

    # Set up monitors before bind to ensure we don't miss early events
    monitor_sub = p_sub.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)
    monitor_pub = p_pub.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)

    p_sub.bind(f"tcp://*:{in_port}")
    p_pub.bind(f"tcp://*:{out_port}")

    logger.info(
        "ZMQ proxy ready for runner coordination: publish port %s, subscribe port %s",
        in_port,
        out_port,
    )

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
                _log_connection_event("publish", evt)

            if monitor_pub in events:
                evt = recv_monitor_message(monitor_pub)
                _log_connection_event("subscribe", evt)

            if p_sub in events:
                msg_parts = p_sub.recv_multipart()
                p_pub.send_multipart(msg_parts)
                _log_forwarded_message(msg_parts)

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
