"""Regression tests for ZMQ transport fixes: ACK origin, ACK-after-accept,
duplicate identifiers, peer expiry, real proxy reachability, finite HWMs."""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import zmq

from aerpawlib._internal.zmq import (
    ZMQ_PROXY_HWM,
    ZMQ_TYPE_ACK,
    ZMQ_TYPE_TRANSITION,
    ZmqTransport,
    apply_proxy_sockopts,
    check_zmq_proxy_reachable,
    run_zmq_proxy,
)
from aerpawlib.v2.runner import ZmqStateMachine, expose_zmq, state
from aerpawlib.v2.testing import MockVehicle

BOUND_S = 5.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fake_transport(identifier: str, **kwargs) -> tuple[ZmqTransport, list[dict]]:
    transport = ZmqTransport(identifier, "127.0.0.1", **kwargs)
    sent: list[dict] = []

    async def fake_send(msg: dict) -> None:
        sent.append(dict(msg))

    transport._pub = object()  # type: ignore[assignment]
    transport.send_raw = fake_send  # type: ignore[method-assign]
    return transport, sent


def _command(req_id: str = "r1") -> dict:
    return {
        "msg_type": ZMQ_TYPE_TRANSITION,
        "from": "leader",
        "identifier": "follower",
        "next_state": "go",
        "req_id": req_id,
        "need_ack": True,
    }


async def _drain(transport: ZmqTransport) -> None:
    if transport._handler_tasks:
        await asyncio.wait_for(asyncio.gather(*transport._handler_tasks, return_exceptions=True), BOUND_S)


# --- #7 ACK origin -------------------------------------------------------------


@pytest.mark.asyncio
async def test_reliable_send_ignores_ack_from_other_peer():
    transport, sent = _fake_transport("leader", ack_retry_interval_s=0.05)

    async def forge_then_real():
        while not sent:
            await asyncio.sleep(0.005)
        req_id = sent[0]["req_id"]
        forged = {"msg_type": ZMQ_TYPE_ACK, "from": "intruder", "identifier": "leader", "req_id": req_id}
        await transport._dispatch(forged)
        await asyncio.sleep(0.1)
        assert not transport._pending_acks[req_id].event.is_set()
        misaddressed = {"msg_type": ZMQ_TYPE_ACK, "from": "follower", "identifier": "someone", "req_id": req_id}
        await transport._dispatch(misaddressed)
        assert not transport._pending_acks[req_id].event.is_set()
        real = {"msg_type": ZMQ_TYPE_ACK, "from": "follower", "identifier": "leader", "req_id": req_id}
        await transport._dispatch(real)

    await asyncio.wait_for(
        asyncio.gather(
            transport.send(
                {"msg_type": ZMQ_TYPE_TRANSITION, "identifier": "follower", "next_state": "go"},
                reliable=True,
                timeout=2.0,
            ),
            forge_then_real(),
        ),
        BOUND_S,
    )


@pytest.mark.asyncio
async def test_forged_ack_alone_does_not_complete_send():
    transport, sent = _fake_transport("leader", ack_retry_interval_s=0.05)

    async def forge():
        while not sent:
            await asyncio.sleep(0.005)
        await transport._dispatch(
            {"msg_type": ZMQ_TYPE_ACK, "from": "intruder", "identifier": "leader", "req_id": sent[0]["req_id"]},
        )

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(
                transport.send(
                    {"msg_type": ZMQ_TYPE_TRANSITION, "identifier": "follower", "next_state": "go"},
                    reliable=True,
                    timeout=0.3,
                ),
                forge(),
            ),
            BOUND_S,
        )


# --- #7 ACK only after the handler accepted -----------------------------------------


@pytest.mark.asyncio
async def test_rejected_message_is_not_acked_and_retry_is_handled():
    transport, sent = _fake_transport("follower")
    results = [False, True]
    calls: list[str] = []

    async def handler(msg: dict) -> bool:
        calls.append(msg["req_id"])
        return results[len(calls) - 1]

    transport.set_handler(handler)
    await transport._dispatch(_command())
    await _drain(transport)
    assert sent == []
    assert "r1" not in transport._seen_req_ids

    await transport._dispatch(_command())
    await _drain(transport)
    assert calls == ["r1", "r1"]
    assert [m["msg_type"] for m in sent] == [ZMQ_TYPE_ACK]
    assert sent[0]["identifier"] == "leader"


@pytest.mark.asyncio
async def test_handler_exception_is_not_acked():
    transport, sent = _fake_transport("follower")

    async def handler(msg: dict) -> None:
        raise RuntimeError("state handler exploded")

    transport.set_handler(handler)
    await transport._dispatch(_command())
    await _drain(transport)
    assert sent == []
    assert "r1" not in transport._seen_req_ids


@pytest.mark.asyncio
async def test_handler_returning_none_is_accepted():
    transport, sent = _fake_transport("follower")

    async def handler(msg: dict) -> None:
        return None

    transport.set_handler(handler)
    await transport._dispatch(_command())
    await _drain(transport)
    assert [m["msg_type"] for m in sent] == [ZMQ_TYPE_ACK]


# --- #8 duplicate identifier / stale peers --------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_identifier_drops_commands():
    transport, sent = _fake_transport("follower")
    calls: list[dict] = []

    async def handler(msg: dict) -> None:
        calls.append(msg)

    transport.set_handler(handler)
    transport._on_hello("follower", "some-other-instance")
    assert transport.duplicate_identifier
    await transport._dispatch(_command())
    await _drain(transport)
    assert calls == []
    assert sent == []


@pytest.mark.asyncio
async def test_stale_peer_expires():
    transport = ZmqTransport("leader", "127.0.0.1", hello_interval_s=0.02, peer_timeout_s=0.2)
    transport.peers["follower"] = time.monotonic() - 10.0
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(transport.wait_for_peers(["follower"], timeout=0.2), BOUND_S)
    assert "follower" not in transport.peers
    transport._on_hello("follower", "x")
    await asyncio.wait_for(transport.wait_for_peers(["follower"], timeout=0.2), BOUND_S)


# --- #15 reachability requires a ZMQ round trip -----------------------------------------


@pytest.fixture
def plain_tcp_listeners():
    socks = []
    accepted = []
    stop = threading.Event()
    for _ in range(2):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(8)
        s.settimeout(0.05)
        socks.append(s)

    def accept_loop():
        while not stop.is_set():
            for s in socks:
                try:
                    conn, _ = s.accept()
                    accepted.append(conn)
                except (TimeoutError, OSError):
                    pass

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    yield [s.getsockname()[1] for s in socks]
    stop.set()
    t.join(timeout=1)
    for c in accepted:
        c.close()
    for s in socks:
        s.close()


def test_non_zmq_listener_is_not_reachable(plain_tcp_listeners):
    in_port, out_port = plain_tcp_listeners
    t0 = time.monotonic()
    assert not check_zmq_proxy_reachable("127.0.0.1", timeout_s=0.3, in_port=in_port, out_port=out_port)
    assert time.monotonic() - t0 < BOUND_S


@pytest.mark.asyncio
async def test_transport_start_against_non_zmq_listener_fails(plain_tcp_listeners):
    in_port, out_port = plain_tcp_listeners
    transport = ZmqTransport("leader", "127.0.0.1", in_port=in_port, out_port=out_port, connect_timeout_s=0.4)
    with pytest.raises(Exception):  # noqa: B017 - TimeoutError from either connect phase
        await asyncio.wait_for(transport.start(), BOUND_S)
    assert not transport.started


def _start_proxy() -> tuple[int, int]:
    in_port, out_port = _free_port(), _free_port()
    threading.Thread(target=run_zmq_proxy, args=(in_port, out_port), daemon=True).start()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if check_zmq_proxy_reachable("127.0.0.1", timeout_s=0.2, in_port=in_port, out_port=out_port):
            return in_port, out_port
        time.sleep(0.01)
    raise RuntimeError("proxy failed to start")


@pytest.mark.asyncio
async def test_transport_start_requires_self_echo_through_real_proxy():
    in_port, out_port = _start_proxy()
    transport = ZmqTransport("solo", "127.0.0.1", in_port=in_port, out_port=out_port)
    try:
        await asyncio.wait_for(transport.start(), BOUND_S)
        assert transport.started
    finally:
        await transport.stop()


# --- #7 end to end: a rejected transition fails the sender ------------------------------


@pytest.mark.asyncio
async def test_unknown_remote_transition_times_out_sender():
    in_port, out_port = _start_proxy()
    outcome: dict[str, object] = {}

    class Leader(ZmqStateMachine):
        @state(name="start", first=True)
        async def start(self, vehicle):
            await self.wait_for_peers(["follower"], timeout=3)
            try:
                await self.transition_runner("follower", "no_such_state", timeout=0.6)
                outcome["result"] = "acked"
            except TimeoutError:
                outcome["result"] = "timeout"
            await self.transition_runner("follower", "go", timeout=3)
            return None

    class Follower(ZmqStateMachine):
        @state(name="idle", first=True)
        async def idle(self, vehicle):
            await asyncio.sleep(0.02)
            return "idle"

        @state(name="go")
        @expose_zmq("go")
        async def go(self, vehicle):
            return None

    leader, follower = Leader(), Follower()
    leader._initialize_zmq_bindings("leader", "127.0.0.1", in_port=in_port, out_port=out_port)
    follower._initialize_zmq_bindings("follower", "127.0.0.1", in_port=in_port, out_port=out_port)
    await asyncio.wait_for(
        asyncio.gather(leader.run(MockVehicle()), follower.run(MockVehicle())),
        timeout=10,
    )
    assert outcome["result"] == "timeout"


# --- #17 finite proxy queues ----------------------------------------------------------------


def test_proxy_sockets_have_finite_hwm():
    ctx = zmq.Context()
    xsub = ctx.socket(zmq.XSUB)
    xpub = ctx.socket(zmq.XPUB)
    try:
        apply_proxy_sockopts(xsub, xpub)
        assert xpub.getsockopt(zmq.SNDHWM) == ZMQ_PROXY_HWM > 0
        assert xsub.getsockopt(zmq.RCVHWM) == ZMQ_PROXY_HWM > 0
    finally:
        xsub.close(linger=0)
        xpub.close(linger=0)
        ctx.term()
