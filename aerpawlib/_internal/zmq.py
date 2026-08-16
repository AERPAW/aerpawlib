"""Shared ZMQ transport for v1/v2 multi-vehicle coordination.

PUB/SUB through an XSUB/XPUB proxy. Control-plane frames are JSON (not pickle).
Publishers wait for EVENT_CONNECTED before sending. HELLO is a presence heartbeat.
Reliable sends retry until an ACK arrives.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import zmq
import zmq.asyncio
from zmq.utils.monitor import parse_monitor_message

logger = logging.getLogger("aerpawlib.zmq")

ZMQ_PROXY_IN_PORT = 5570
ZMQ_PROXY_OUT_PORT = 5571
ZMQ_REACHABILITY_TIMEOUT_S = 2.0
ZMQ_CONNECT_TIMEOUT_S = 2.0
ZMQ_HELLO_INTERVAL_S = 0.2
ZMQ_ACK_RETRY_INTERVAL_S = 0.15
ZMQ_RELIABLE_TIMEOUT_S = 10.0
ZMQ_GOODBYE_TIMEOUT_S = 0.2
ZMQ_SUB_SETTLE_S = 0.05
ZMQ_SEEN_REQ_IDS_MAX = 2048

ZMQ_TYPE_TRANSITION = "state_transition"
ZMQ_TYPE_FIELD_REQUEST = "field_request"
ZMQ_TYPE_FIELD_CALLBACK = "field_callback"
ZMQ_TYPE_HELLO = "hello"
ZMQ_TYPE_GOODBYE = "goodbye"
ZMQ_TYPE_ACK = "ack"

_BROADCAST_TYPES = frozenset({ZMQ_TYPE_HELLO, ZMQ_TYPE_GOODBYE})
_COORD_TYPE = "Coordinate"
_VECTOR_TYPE = "VectorNED"

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "lat") and hasattr(obj, "lon"):
        return {
            "__type__": _COORD_TYPE,
            "lat": obj.lat,
            "lon": obj.lon,
            "alt": getattr(obj, "alt", 0.0),
        }
    if hasattr(obj, "north") and hasattr(obj, "east"):
        return {
            "__type__": _VECTOR_TYPE,
            "north": obj.north,
            "east": obj.east,
            "down": getattr(obj, "down", 0.0),
        }
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def encode_message(msg: dict[str, Any]) -> bytes:
    """Serialize a runner message to a JSON UTF-8 frame."""
    return json.dumps(msg, default=_json_default, separators=(",", ":")).encode("utf-8")


def decode_message(data: bytes) -> dict[str, Any] | None:
    """Parse a JSON runner message. Returns None if the frame is not a dict."""
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def decode_value(
    obj: Any,
    *,
    coordinate_cls: Any | None = None,
    vector_cls: Any | None = None,
) -> Any:
    """Reconstruct Coordinate/VectorNED tagged values from JSON."""
    if not isinstance(obj, dict) or "__type__" not in obj:
        return obj
    kind = obj.get("__type__")
    if kind == _COORD_TYPE and coordinate_cls is not None:
        return coordinate_cls(obj["lat"], obj["lon"], obj.get("alt", 0.0))
    if kind == _VECTOR_TYPE and vector_cls is not None:
        return vector_cls(obj["north"], obj["east"], obj.get("down", 0.0))
    return obj


def _set_sockopt(sock: zmq.Socket, option: int, value: int) -> None:
    try:
        sock.setsockopt(option, value)
    except (zmq.ZMQError, AttributeError):
        pass


def apply_runner_sockopts(sock: zmq.Socket) -> None:
    """Apply production sockopts to a runner PUB/SUB socket."""
    _set_sockopt(sock, zmq.LINGER, 0)
    _set_sockopt(sock, zmq.IMMEDIATE, 1)
    _set_sockopt(sock, zmq.SNDHWM, 1000)
    _set_sockopt(sock, zmq.RCVHWM, 1000)
    _set_sockopt(sock, zmq.TCP_KEEPALIVE, 1)
    _set_sockopt(sock, zmq.HEARTBEAT_IVL, 2000)
    _set_sockopt(sock, zmq.HEARTBEAT_TIMEOUT, 10000)
    _set_sockopt(sock, zmq.RECONNECT_IVL, 100)
    _set_sockopt(sock, zmq.RECONNECT_IVL_MAX, 5000)


def apply_proxy_sockopts(xsub: zmq.Socket, xpub: zmq.Socket) -> None:
    """Apply production sockopts to proxy sockets."""
    _set_sockopt(xsub, zmq.LINGER, 0)
    _set_sockopt(xpub, zmq.LINGER, 0)
    _set_sockopt(xpub, zmq.XPUB_NODROP, 1)
    _set_sockopt(xpub, zmq.SNDHWM, 0)
    _set_sockopt(xsub, zmq.RCVHWM, 0)
    _set_sockopt(xpub, zmq.XPUB_VERBOSE, 1)


async def _recv_monitor(monitor: zmq.asyncio.Socket) -> dict[str, Any]:
    frames = await monitor.recv_multipart()
    return parse_monitor_message(frames)


async def wait_monitor_connected(
    monitor: zmq.asyncio.Socket,
    timeout_s: float = ZMQ_CONNECT_TIMEOUT_S,
) -> None:
    """Block until *monitor* reports EVENT_CONNECTED or *timeout_s* elapses."""
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"ZMQ socket did not connect within {timeout_s:.1f}s",
            )
        if await monitor.poll(timeout=max(1, int(remaining * 1000))):
            evt = await _recv_monitor(monitor)
            if evt.get("event") == zmq.EVENT_CONNECTED:
                return


def check_zmq_proxy_reachable(
    proxy_addr: str,
    timeout_s: float = ZMQ_REACHABILITY_TIMEOUT_S,
    in_port: int | str = ZMQ_PROXY_IN_PORT,
    out_port: int | str = ZMQ_PROXY_OUT_PORT,
) -> bool:
    """Return True only if both proxy TCP ports accept connections."""
    for port in (in_port, out_port):
        try:
            with socket.create_connection((proxy_addr, int(port)), timeout=timeout_s):
                pass
        except (OSError, ValueError):
            return False
    return True


def _format_runner_message(msg: dict[str, Any]) -> str:
    msg_type = msg.get("msg_type")
    sender = msg.get("from", "?")
    recipient = msg.get("identifier", "?")
    if msg_type == ZMQ_TYPE_HELLO:
        return f"hello client connected: name={sender!r}"
    if msg_type == ZMQ_TYPE_GOODBYE:
        return f"goodbye client disconnected: name={sender!r}"
    if msg_type == ZMQ_TYPE_TRANSITION:
        return f"state_transition {sender} -> {recipient}: next_state={msg.get('next_state')!r}"
    if msg_type == ZMQ_TYPE_FIELD_REQUEST:
        return f"field_request {sender} -> {recipient}: field={msg.get('field')!r}"
    if msg_type == ZMQ_TYPE_FIELD_CALLBACK:
        return f"field_callback {sender} -> {recipient}: field={msg.get('field')!r}, value={msg.get('value')!r}"
    if msg_type == ZMQ_TYPE_ACK:
        return f"ack {sender} -> {recipient}: req_id={msg.get('req_id')!r}"
    return f"unrecognized runner message from={sender!r} to={recipient!r}: {msg}"


def _log_forwarded_message(msg_parts: list[bytes]) -> None:
    for part in msg_parts:
        parsed = decode_message(part)
        if parsed is not None:
            logger.info("Forwarded %s", _format_runner_message(parsed))
            return
    raw_reprs = [part[:50].hex() + ("..." if len(part) > 50 else "") for part in msg_parts]
    logger.warning("Forwarded non-runner payload (raw hex): %s", raw_reprs)


def _log_connection_event(channel: str, evt: dict[str, Any]) -> None:
    event_id = evt.get("event")
    if event_id == zmq.EVENT_ACCEPTED:
        logger.info("Runner %s client connected", channel)
    elif event_id == zmq.EVENT_DISCONNECTED:
        logger.info("Runner %s client disconnected", channel)


def _log_subscription_flow(msg_parts: list[bytes]) -> None:
    for part in msg_parts:
        if not part:
            continue
        action = part[0]
        topic_str = part[1:].decode("utf-8", errors="ignore")
        if action == 1:
            logger.debug("Runner subscribed to topic %r", topic_str or "*")
        elif action == 0:
            logger.debug("Runner unsubscribed from topic %r", topic_str or "*")
        else:
            logger.warning("Unknown subscription action %s for topic %r", action, topic_str)


def run_zmq_proxy(
    in_port: int | str = ZMQ_PROXY_IN_PORT,
    out_port: int | str = ZMQ_PROXY_OUT_PORT,
    bind: str = "*",
) -> None:
    """Blocking XSUB/XPUB forwarder with connection and JSON message logging."""
    ctx = zmq.Context()
    p_sub = ctx.socket(zmq.XSUB)
    p_pub = ctx.socket(zmq.XPUB)
    apply_proxy_sockopts(p_sub, p_pub)

    monitor_sub = p_sub.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)
    monitor_pub = p_pub.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)

    p_sub.bind(f"tcp://{bind}:{in_port}")
    p_pub.bind(f"tcp://{bind}:{out_port}")

    logger.info(
        "ZMQ proxy ready for runner coordination: publish port %s, subscribe port %s, bind %s",
        in_port,
        out_port,
        bind,
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
                from zmq.utils.monitor import recv_monitor_message

                _log_connection_event("publish", recv_monitor_message(monitor_sub))
            if monitor_pub in events:
                from zmq.utils.monitor import recv_monitor_message

                _log_connection_event("subscribe", recv_monitor_message(monitor_pub))
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
        for sock in (monitor_sub, monitor_pub, p_sub, p_pub):
            try:
                poller.unregister(sock)
            except (KeyError, zmq.ZMQError):
                pass
            sock.close(linger=0)
        ctx.term()


def proxy_cli(argv: list[str] | None = None) -> int:
    """CLI entry for aerpawlib-run-proxy."""
    parser = argparse.ArgumentParser(description="AERPAW ZMQ XSUB/XPUB proxy for multi-vehicle runners")
    parser.add_argument("--in-port", type=int, default=ZMQ_PROXY_IN_PORT, help="XSUB bind port (publishers connect here)")
    parser.add_argument("--out-port", type=int, default=ZMQ_PROXY_OUT_PORT, help="XPUB bind port (subscribers connect here)")
    parser.add_argument("--bind", default="*", help="Bind address (default: all interfaces)")
    args = parser.parse_args(argv)
    try:
        run_zmq_proxy(in_port=args.in_port, out_port=args.out_port, bind=args.bind)
    except Exception as e:
        logger.error("ZMQ proxy failed: %s", e)
        return 1
    return 0


@dataclass
class _PendingAck:
    event: asyncio.Event
    req_id: str


class ZmqTransport:
    """Async PUB/SUB transport with connect-wait, HELLO presence, and ACK retry."""

    def __init__(
        self,
        identifier: str,
        proxy_addr: str,
        *,
        in_port: int | str = ZMQ_PROXY_IN_PORT,
        out_port: int | str = ZMQ_PROXY_OUT_PORT,
        connect_timeout_s: float = ZMQ_CONNECT_TIMEOUT_S,
        hello_interval_s: float = ZMQ_HELLO_INTERVAL_S,
        ack_retry_interval_s: float = ZMQ_ACK_RETRY_INTERVAL_S,
    ) -> None:
        self.identifier = identifier
        self.proxy_addr = proxy_addr
        self.in_port = int(in_port)
        self.out_port = int(out_port)
        self.connect_timeout_s = connect_timeout_s
        self.hello_interval_s = hello_interval_s
        self.ack_retry_interval_s = ack_retry_interval_s
        self.instance_id = uuid.uuid4().hex
        self.peers: dict[str, float] = {}
        self.duplicate_identifier = False

        self._handler: MessageHandler | None = None
        self._ctx: zmq.asyncio.Context | None = None
        self._pub: zmq.asyncio.Socket | None = None
        self._sub: zmq.asyncio.Socket | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._pending_acks: dict[str, _PendingAck] = {}
        self._handler_tasks: set[asyncio.Task] = set()
        self._seen_req_ids: OrderedDict[str, None] = OrderedDict()

    def set_handler(self, handler: MessageHandler) -> None:
        """Set the async callback invoked for application messages."""
        self._handler = handler

    @property
    def started(self) -> bool:
        return self._running and self._pub is not None and self._sub is not None

    async def start(self) -> None:
        """Connect PUB and SUB, wait until both are connected, start loops."""
        if self._running:
            return
        self._ctx = zmq.asyncio.Context()
        pub = self._ctx.socket(zmq.PUB)
        sub = self._ctx.socket(zmq.SUB)
        apply_runner_sockopts(pub)
        apply_runner_sockopts(sub)
        sub.setsockopt_string(zmq.SUBSCRIBE, "")

        # Attach monitors before connect() so EVENT_CONNECTED cannot be missed.
        pub_mon = pub.get_monitor_socket(zmq.EVENT_CONNECTED)
        sub_mon = sub.get_monitor_socket(zmq.EVENT_CONNECTED)
        pub.connect(f"tcp://{self.proxy_addr}:{self.in_port}")
        sub.connect(f"tcp://{self.proxy_addr}:{self.out_port}")
        try:
            await asyncio.gather(
                wait_monitor_connected(pub_mon, self.connect_timeout_s),
                wait_monitor_connected(sub_mon, self.connect_timeout_s),
            )
        except Exception:
            pub.close(linger=0)
            sub.close(linger=0)
            pub_mon.close(linger=0)
            sub_mon.close(linger=0)
            self._ctx.destroy(linger=0)
            self._ctx = None
            raise
        finally:
            for mon, sock in ((pub_mon, pub), (sub_mon, sub)):
                try:
                    sock.disable_monitor()
                except zmq.ZMQError:
                    pass
                mon.close(linger=0)

        await asyncio.sleep(ZMQ_SUB_SETTLE_S)
        self._pub = pub
        self._sub = sub
        self._running = True
        logger.info(
            "ZMQ sockets connected to proxy %s (pub :%s, sub :%s, id=%s)",
            self.proxy_addr,
            self.in_port,
            self.out_port,
            self.identifier,
        )
        self._tasks = [
            asyncio.create_task(self._recv_loop(), name="zmq-recv"),
            asyncio.create_task(self._hello_loop(), name="zmq-hello"),
        ]

    async def stop(self) -> None:
        """Send goodbye, cancel loops, and destroy the context."""
        self._running = False
        if self._pub is not None:
            try:
                await asyncio.wait_for(
                    self._pub.send(encode_message(self._presence_msg(ZMQ_TYPE_GOODBYE))),
                    timeout=ZMQ_GOODBYE_TIMEOUT_S,
                )
            except Exception:
                pass
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        for task in list(self._handler_tasks):
            task.cancel()
        if self._handler_tasks:
            await asyncio.gather(*self._handler_tasks, return_exceptions=True)
        self._handler_tasks.clear()
        if self._pub is not None:
            self._pub.close(linger=0)
            self._pub = None
        if self._sub is not None:
            self._sub.close(linger=0)
            self._sub = None
        if self._ctx is not None:
            self._ctx.destroy(linger=0)
            self._ctx = None

    def _presence_msg(self, msg_type: str) -> dict[str, Any]:
        return {
            "msg_type": msg_type,
            "from": self.identifier,
            "instance_id": self.instance_id,
        }

    async def send_raw(self, msg: dict[str, Any]) -> None:
        """Send one frame. Raises if the transport is not started."""
        if self._pub is None:
            raise RuntimeError("ZMQ transport is not started")
        await self._pub.send(encode_message(msg))

    async def send(
        self,
        msg: dict[str, Any],
        *,
        reliable: bool = False,
        timeout: float = ZMQ_RELIABLE_TIMEOUT_S,
    ) -> None:
        """Send a message. If reliable=True, retry until ACK or timeout."""
        if self._pub is None:
            raise RuntimeError("ZMQ not initialized; call _initialize_zmq_bindings first")
        msg.setdefault("from", self.identifier)
        if not reliable:
            await self.send_raw(msg)
            return

        req_id = msg.get("req_id") or uuid.uuid4().hex
        msg["req_id"] = req_id
        msg["need_ack"] = True
        pending = _PendingAck(event=asyncio.Event(), req_id=req_id)
        self._pending_acks[req_id] = pending
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"ZMQ reliable send to {msg.get('identifier')!r} timed out after {timeout:.1f}s (req_id={req_id})",
                    )
                await self.send_raw(msg)
                wait = min(self.ack_retry_interval_s, remaining)
                try:
                    await asyncio.wait_for(pending.event.wait(), timeout=wait)
                    return
                except asyncio.TimeoutError:
                    continue
        finally:
            self._pending_acks.pop(req_id, None)

    async def wait_for_peers(
        self,
        identifiers: list[str],
        timeout: float = 30.0,
    ) -> None:
        """Block until every identifier has sent HELLO, or raise TimeoutError."""
        wanted = set(identifiers)
        deadline = time.monotonic() + timeout
        while True:
            missing = wanted - set(self.peers)
            if not missing:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for ZMQ peers {sorted(missing)} (have {sorted(self.peers)})",
                )
            await asyncio.sleep(min(self.hello_interval_s, remaining))

    async def _hello_loop(self) -> None:
        try:
            while self._running:
                try:
                    await self.send_raw(self._presence_msg(ZMQ_TYPE_HELLO))
                except Exception as e:
                    logger.warning("ZMQ hello send failed: %s", e)
                await asyncio.sleep(self.hello_interval_s)
        except asyncio.CancelledError:
            return

    async def _recv_loop(self) -> None:
        assert self._sub is not None
        try:
            while self._running:
                try:
                    frame = await self._sub.recv()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("ZMQ recv error: %s", e)
                    continue
                msg = decode_message(frame)
                if msg is None:
                    logger.warning("ZMQ dropped non-JSON or non-dict frame")
                    continue
                try:
                    await self._dispatch(msg)
                except Exception:
                    logger.exception("ZMQ dispatch error")
        except asyncio.CancelledError:
            return

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("msg_type")
        sender = msg.get("from")

        if msg_type == ZMQ_TYPE_HELLO:
            self._on_hello(sender, msg.get("instance_id"))
            return
        if msg_type == ZMQ_TYPE_GOODBYE:
            if isinstance(sender, str) and sender != self.identifier:
                self.peers.pop(sender, None)
            return
        if msg_type == ZMQ_TYPE_ACK:
            req_id = msg.get("req_id")
            if isinstance(req_id, str) and req_id in self._pending_acks:
                self._pending_acks[req_id].event.set()
            return

        recipient = msg.get("identifier")
        if recipient != self.identifier:
            return

        req_id = msg.get("req_id")
        if msg.get("need_ack") and isinstance(req_id, str) and self._pub is not None:
            ack = {
                "msg_type": ZMQ_TYPE_ACK,
                "from": self.identifier,
                "identifier": sender,
                "req_id": req_id,
            }
            try:
                await self.send_raw(ack)
            except Exception as e:
                logger.warning("ZMQ failed to send ack: %s", e)
            if req_id in self._seen_req_ids:
                return
            self._seen_req_ids[req_id] = None
            while len(self._seen_req_ids) > ZMQ_SEEN_REQ_IDS_MAX:
                self._seen_req_ids.popitem(last=False)

        if self._handler is None:
            return
        task = asyncio.create_task(self._handler(msg))
        self._handler_tasks.add(task)
        task.add_done_callback(self._handler_tasks.discard)

    def _on_hello(self, sender: object, instance_id: object) -> None:
        if not isinstance(sender, str) or not sender:
            return
        if sender == self.identifier:
            if isinstance(instance_id, str) and instance_id != self.instance_id:
                if not self.duplicate_identifier:
                    logger.error(
                        "Duplicate ZMQ identifier %r (local instance %s, other %s)",
                        sender,
                        self.instance_id,
                        instance_id,
                    )
                    self.duplicate_identifier = True
            return
        self.peers[sender] = time.monotonic()
