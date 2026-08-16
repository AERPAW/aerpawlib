"""End-to-end ZMQ runner tests through a live proxy. No sleep(0.5) delivery hacks."""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

from aerpawlib._internal.zmq import check_zmq_proxy_reachable, run_zmq_proxy
from aerpawlib.v2.runner import ZmqStateMachine, expose_field_zmq, expose_zmq, state
from aerpawlib.v2.testing import MockVehicle
from aerpawlib.v2.types import Coordinate


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _start_proxy() -> tuple[int, int]:
    in_port = _free_port()
    out_port = _free_port()
    threading.Thread(target=run_zmq_proxy, args=(in_port, out_port), daemon=True).start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if check_zmq_proxy_reachable("127.0.0.1", timeout_s=0.05, in_port=in_port, out_port=out_port):
            return in_port, out_port
        time.sleep(0.01)
    raise RuntimeError("proxy failed to start")


def _bind(runner: ZmqStateMachine, ident: str, in_port: int, out_port: int) -> None:
    runner._initialize_zmq_bindings(ident, "127.0.0.1", in_port=in_port, out_port=out_port)


@pytest.mark.asyncio
async def test_first_transition_is_delivered_without_sleep():
    in_port, out_port = _start_proxy()

    class Leader(ZmqStateMachine):
        @state(name="start", first=True)
        async def start(self, vehicle):
            await self.wait_for_peers(["follower"], timeout=5)
            await self.transition_runner("follower", "go")
            return None

    class Follower(ZmqStateMachine):
        def __init__(self) -> None:
            super().__init__()
            self.visited: list[str] = []

        @state(name="idle", first=True)
        async def idle(self, vehicle):
            if "go" in self.visited:
                return None
            await asyncio.sleep(0.02)
            return "idle"

        @expose_zmq("go")
        @state(name="go")
        async def go(self, vehicle):
            self.visited.append("go")
            return None

    leader = Leader()
    follower = Follower()
    _bind(leader, "leader", in_port, out_port)
    _bind(follower, "follower", in_port, out_port)

    await asyncio.wait_for(
        asyncio.gather(leader.run(MockVehicle()), follower.run(MockVehicle())),
        timeout=8,
    )
    assert follower.visited == ["go"]


@pytest.mark.asyncio
async def test_late_joiner_receives_after_hello():
    in_port, out_port = _start_proxy()

    early_seen_late = asyncio.Event()
    late_seen_early = asyncio.Event()

    class Early(ZmqStateMachine):
        @state(name="start", first=True)
        async def start(self, vehicle):
            await self.wait_for_peers(["late"], timeout=5)
            early_seen_late.set()
            await asyncio.wait_for(late_seen_early.wait(), timeout=5)
            return None

    class Late(ZmqStateMachine):
        @state(name="start", first=True)
        async def start(self, vehicle):
            await self.wait_for_peers(["early"], timeout=5)
            late_seen_early.set()
            await asyncio.wait_for(early_seen_late.wait(), timeout=5)
            return None

    early = Early()
    _bind(early, "early", in_port, out_port)
    early_task = asyncio.create_task(early.run(MockVehicle()))
    await asyncio.sleep(0.3)

    late = Late()
    _bind(late, "late", in_port, out_port)
    await asyncio.wait_for(
        asyncio.gather(early_task, late.run(MockVehicle())),
        timeout=8,
    )


@pytest.mark.asyncio
async def test_query_field_coordinate_round_trip():
    in_port, out_port = _start_proxy()
    target = Coordinate(35.7, -78.6, 12.0)

    class Provider(ZmqStateMachine):
        @state(name="idle", first=True)
        async def idle(self, vehicle):
            await asyncio.sleep(0.05)
            if getattr(self, "_done", False):
                return None
            return "idle"

        @expose_field_zmq("position")
        async def position(self, vehicle):
            return target

    class Consumer(ZmqStateMachine):
        def __init__(self) -> None:
            super().__init__()
            self.result = None

        @state(name="start", first=True)
        async def start(self, vehicle):
            await self.wait_for_peers(["provider"], timeout=5)
            self.result = await self.query_field("provider", "position", timeout=5)
            return None

    provider = Provider()
    consumer = Consumer()
    _bind(provider, "provider", in_port, out_port)
    _bind(consumer, "consumer", in_port, out_port)

    async def _stop_provider() -> None:
        while consumer.result is None:
            await asyncio.sleep(0.02)
        provider._done = True

    await asyncio.wait_for(
        asyncio.gather(
            provider.run(MockVehicle()),
            consumer.run(MockVehicle()),
            _stop_provider(),
        ),
        timeout=8,
    )
    assert isinstance(consumer.result, Coordinate)
    assert consumer.result.lat == pytest.approx(target.lat)
    assert consumer.result.lon == pytest.approx(target.lon)
    assert consumer.result.alt == pytest.approx(target.alt)


@pytest.mark.asyncio
async def test_non_dict_payload_does_not_kill_recv_loop():
    in_port, out_port = _start_proxy()

    class Receiver(ZmqStateMachine):
        def __init__(self) -> None:
            super().__init__()
            self.got = False

        @state(name="idle", first=True)
        async def idle(self, vehicle):
            if self.got:
                return None
            await asyncio.sleep(0.02)
            return "idle"

        @state(name="mark")
        async def mark(self, vehicle):
            self.got = True
            return None

    class Sender(ZmqStateMachine):
        @state(name="start", first=True)
        async def start(self, vehicle):
            await self.wait_for_peers(["receiver"], timeout=5)
            assert self._zmq_transport is not None
            await self._zmq_transport._pub.send(b"not-json")  # type: ignore[union-attr]
            await self.transition_runner("receiver", "mark")
            return None

    receiver = Receiver()
    sender = Sender()
    _bind(receiver, "receiver", in_port, out_port)
    _bind(sender, "sender", in_port, out_port)
    await asyncio.wait_for(
        asyncio.gather(receiver.run(MockVehicle()), sender.run(MockVehicle())),
        timeout=8,
    )
    assert receiver.got


@pytest.mark.asyncio
async def test_duplicate_req_id_does_not_rerun_handler():
    from aerpawlib._internal.zmq import ZMQ_TYPE_ACK, ZMQ_TYPE_TRANSITION, ZmqTransport

    transport = ZmqTransport("follower", "127.0.0.1")
    calls: list[dict] = []

    async def handler(msg: dict) -> None:
        calls.append(msg)

    transport.set_handler(handler)
    sent: list[dict] = []

    async def fake_send(msg: dict) -> None:
        sent.append(msg)

    transport._pub = object()  # type: ignore[assignment]
    transport.send_raw = fake_send  # type: ignore[method-assign]

    msg = {
        "msg_type": ZMQ_TYPE_TRANSITION,
        "from": "leader",
        "identifier": "follower",
        "next_state": "go",
        "req_id": "dup-1",
        "need_ack": True,
    }
    await transport._dispatch(msg)
    await transport._dispatch(msg)
    if transport._handler_tasks:
        await asyncio.gather(*transport._handler_tasks)
    assert len(calls) == 1
    assert all(frame.get("msg_type") == ZMQ_TYPE_ACK for frame in sent)
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_reliable_send_retries_until_late_ack():
    from aerpawlib._internal.zmq import ZMQ_TYPE_TRANSITION, ZmqTransport

    transport = ZmqTransport("leader", "127.0.0.1", ack_retry_interval_s=0.05)
    sent: list[dict] = []

    async def fake_send(msg: dict) -> None:
        sent.append(dict(msg))

    transport._pub = object()  # type: ignore[assignment]
    transport.send_raw = fake_send  # type: ignore[method-assign]

    async def ack_after_retry() -> None:
        while not sent:
            await asyncio.sleep(0.01)
        req_id = sent[0]["req_id"]
        await asyncio.sleep(0.12)
        transport._pending_acks[req_id].event.set()

    await asyncio.wait_for(
        asyncio.gather(
            transport.send(
                {
                    "msg_type": ZMQ_TYPE_TRANSITION,
                    "identifier": "follower",
                    "next_state": "go",
                },
                reliable=True,
                timeout=1.0,
            ),
            ack_after_retry(),
        ),
        timeout=2.0,
    )
    assert len(sent) >= 2
