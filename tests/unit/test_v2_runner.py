"""Unit tests for aerpawlib v2 BasicRunner, StateMachine, and ZmqStateMachine."""

import asyncio
import pytest

from aerpawlib.v2.runner import (
    BasicRunner,
    StateMachine,
    ZmqStateMachine,
    entrypoint,
    state,
    expose_zmq,
    expose_field_zmq,
    timed_state,
    background,
    at_init,
)
from aerpawlib.v2.constants import (
    ZMQ_TYPE_TRANSITION,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_FIELD_CALLBACK,
)
from aerpawlib.v2.exceptions import (
    HeartbeatLostError,
    NoEntrypointError,
    NoInitialStateError,
    MultipleInitialStatesError,
    RunnerError,
)
from aerpawlib.v2.safety.connection import ConnectionHandler
from aerpawlib.v2.testing import MockVehicle


class TestBasicRunner:
    """BasicRunner with MockVehicle."""

    @pytest.mark.asyncio
    async def test_entrypoint_runs(self):
        ran = []

        class MinimalRunner(BasicRunner):
            @entrypoint
            async def run(self, vehicle):
                ran.append(1)

        runner = MinimalRunner()
        await runner.run(MockVehicle())
        assert ran == [1]

    @pytest.mark.asyncio
    async def test_no_entrypoint_raises(self):
        class NoEntrypoint(BasicRunner):
            pass

        with pytest.raises(NoEntrypointError):
            await NoEntrypoint().run(MockVehicle())

    @pytest.mark.asyncio
    async def test_multiple_entrypoints_raises(self):
        # Py <3.12 wraps __set_name__ failures in RuntimeError; 3.12+ raises RunnerError.
        with pytest.raises((RuntimeError, RunnerError)) as excinfo:

            class MultiEntry(BasicRunner):
                @entrypoint
                async def run1(self, vehicle):
                    pass

                @entrypoint
                async def run2(self, vehicle):
                    pass

        err = excinfo.value
        inner = err.__cause__ if isinstance(err, RuntimeError) else err
        assert isinstance(inner, RunnerError)
        assert "Only one @entrypoint" in str(inner)


class TestStateMachine:
    """StateMachine with MockVehicle."""

    @pytest.mark.asyncio
    async def test_state_transitions(self):
        order = []

        class SM(StateMachine):
            @state(name="a", first=True)
            async def a(self, vehicle):
                order.append("a")
                return "b"

            @state(name="b")
            async def b(self, vehicle):
                order.append("b")
                return None

        await SM().run(MockVehicle())
        assert order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_timed_state_duration(self):
        order = []

        class SM(StateMachine):
            @timed_state(name="t", duration=0.1, first=True)
            async def t(self, vehicle):
                order.append("t")
                return None

        await SM().run(MockVehicle())
        assert "t" in order

    @pytest.mark.asyncio
    async def test_background_task_starts(self):
        started = []

        class SM(StateMachine):
            @background
            async def bg(self, vehicle):
                started.append(1)
                import asyncio

                while True:
                    await asyncio.sleep(0.1)

            @state(name="s", first=True)
            async def s(self, vehicle):
                import asyncio

                await asyncio.sleep(0.15)
                return None

        await SM().run(MockVehicle())
        assert len(started) == 1

    @pytest.mark.asyncio
    async def test_at_init_runs_before_states(self):
        order = []

        class SM(StateMachine):
            @at_init
            async def init_task(self, vehicle):
                order.append("init")

            @state(name="s", first=True)
            async def s(self, vehicle):
                order.append("s")
                return None

        await SM().run(MockVehicle())
        assert order == ["init", "s"]

    @pytest.mark.asyncio
    async def test_no_initial_state_raises(self):
        class SM(StateMachine):
            @state(name="a")
            async def a(self, vehicle):
                return None

        with pytest.raises(NoInitialStateError):
            await SM().run(MockVehicle())

    @pytest.mark.asyncio
    async def test_multiple_initial_states_raises(self):
        with pytest.raises((RuntimeError, MultipleInitialStatesError)) as excinfo:

            class SM(StateMachine):
                @state(name="a", first=True)
                async def a(self, vehicle):
                    return None

                @state(name="b", first=True)
                async def b(self, vehicle):
                    return None

        err = excinfo.value
        inner = err.__cause__ if isinstance(err, RuntimeError) else err
        assert isinstance(inner, MultipleInitialStatesError)

    @pytest.mark.asyncio
    async def test_inherited_background_preserves_parent_initial_state(self):
        calls = []

        class Base(StateMachine):
            @state(name="start", first=True)
            async def start(self, vehicle):
                calls.append("start")
                return None

        class Child(Base):
            @background
            async def bg(self, vehicle):
                await asyncio.sleep(0)

        await Child().run(MockVehicle())
        assert calls == ["start"]

    @pytest.mark.asyncio
    async def test_background_futures_reset_between_runs(self):
        class SM(StateMachine):
            @background
            async def bg(self, vehicle):
                await asyncio.sleep(0.01)

            @state(name="s", first=True)
            async def s(self, vehicle):
                await asyncio.sleep(0.02)
                return None

        sm = SM()
        await sm.run(MockVehicle())
        assert len(sm._background_futures) == 1
        await sm.run(MockVehicle())
        assert len(sm._background_futures) == 1

    def test_stacked_state_and_timed_state_raises(self):
        with pytest.raises(RunnerError) as excinfo:

            class Bad(StateMachine):
                @state(name="a", first=True)
                @timed_state(name="a", duration=1.0)
                async def a(self, vehicle):
                    return None

        assert "more than one of @state/@timed_state" in str(excinfo.value)

    def test_stacked_timed_state_and_state_raises(self):
        with pytest.raises(RunnerError) as excinfo:

            class Bad(StateMachine):
                @timed_state(name="a", duration=1.0)
                @state(name="a", first=True)
                async def a(self, vehicle):
                    return None

        assert "more than one of @state/@timed_state" in str(excinfo.value)


class TestZmqStateMachine:
    """Unit tests for ZmqStateMachine (no live ZMQ proxy needed)."""

    def test_run_without_init_raises(self):
        """run() before _initialize_zmq_bindings raises RunnerError."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        with pytest.raises(RunnerError):
            import asyncio

            asyncio.run(Z().run(MockVehicle()))

    def test_initialize_zmq_bindings_sets_attrs(self):
        """_initialize_zmq_bindings sets identifier and proxy server."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("myid", "127.0.0.1")
        assert z._zmq_identifier == "myid"
        assert z._zmq_proxy_server == "127.0.0.1"
        # Send queue is created in run() when an event loop is running (Py3.9 compat).
        assert z._zmq_send_queue is None
        assert z._zmq_pending_fields == {}
        # Clean up context so it doesn't leak
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    def test_expose_zmq_then_state_registers_exposed_state(self):
        class Z(ZmqStateMachine):
            @expose_zmq("remote")
            @state(name="internal", first=True)
            async def s(self, vehicle):
                return None

        cfg = Z.config
        assert cfg.initial_state == "internal"
        assert any(
            spec.name == "internal" and spec.method_name == "s" for spec in cfg.states
        )
        assert cfg.exposed_states["remote"] == "internal"

    def test_state_then_expose_zmq_registers_exposed_state(self):
        class Z(ZmqStateMachine):
            @state(name="internal", first=True)
            @expose_zmq("remote")
            async def s(self, vehicle):
                return None

        cfg = Z.config
        assert cfg.initial_state == "internal"
        assert any(
            spec.name == "internal" and spec.method_name == "s" for spec in cfg.states
        )
        assert cfg.exposed_states["remote"] == "internal"

    def test_expose_zmq_without_state_raises(self):
        with pytest.raises((RuntimeError, RunnerError)) as excinfo:

            class Z(ZmqStateMachine):
                @expose_zmq("remote")
                async def no_state(self, vehicle):
                    return None

        err = excinfo.value
        inner = err.__cause__ if isinstance(err, RuntimeError) else err
        assert isinstance(inner, RunnerError)
        assert "only be used on @state/@timed_state" in str(inner)


class TestConnectionHandler:
    @pytest.mark.asyncio
    async def test_times_out_without_telemetry_ticks_wait_api(self):
        handler = ConnectionHandler(
            MockVehicle(),
            heartbeat_timeout=0.1,
            start_delay=0.0,
        )
        monitor = handler.start()
        disconnect_future = handler.get_disconnect_future()

        with pytest.raises(HeartbeatLostError):
            await asyncio.wait_for(disconnect_future, timeout=1.5)

        handler.stop()
        monitor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await monitor

    @pytest.mark.asyncio
    async def test_handle_transition_message(self):
        """TRANSITION message sets the state override attributes."""

        class Z(ZmqStateMachine):
            @state(name="a", first=True)
            async def a(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        msg = {
            "msg_type": ZMQ_TYPE_TRANSITION,
            "from": "other",
            "identifier": "me",
            "next_state": "target_state",
        }
        await z._zmq_handle_message(MockVehicle(), msg)
        assert z._override_next_state_transition is True
        assert z._next_state_overr == "target_state"
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_handle_field_callback_sets_value_and_signals_event(self):
        """FIELD_CALLBACK stores value and sets the asyncio.Event for a pending query."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        event = asyncio.Event()
        z._zmq_pending_fields["sender"] = {"myfield": event}

        msg = {
            "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
            "from": "sender",
            "identifier": "me",
            "field": "myfield",
            "value": 42,
        }
        await z._zmq_handle_message(MockVehicle(), msg)
        assert z._zmq_pending_fields["sender"]["myfield"] == 42
        assert event.is_set()
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_unsolicited_field_callback_stored_without_error(self):
        """An unsolicited FIELD_CALLBACK (no pending Event) is stored without raising."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        # No entry in _zmq_pending_fields for "stranger"

        msg = {
            "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
            "from": "stranger",
            "identifier": "me",
            "field": "data",
            "value": "hello",
        }
        await z._zmq_handle_message(MockVehicle(), msg)
        assert z._zmq_pending_fields["stranger"]["data"] == "hello"
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_malformed_messages_do_not_raise(self):
        """Malformed ZMQ messages (missing keys) are logged and silently dropped."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        vehicle = MockVehicle()
        # TRANSITION without next_state
        await z._zmq_handle_message(
            vehicle, {"msg_type": ZMQ_TYPE_TRANSITION, "identifier": "me"}
        )
        # FIELD_REQUEST without field
        await z._zmq_handle_message(
            vehicle,
            {"msg_type": ZMQ_TYPE_FIELD_REQUEST, "identifier": "me", "from": "x"},
        )
        # FIELD_CALLBACK without field
        await z._zmq_handle_message(
            vehicle,
            {"msg_type": ZMQ_TYPE_FIELD_CALLBACK, "identifier": "me", "from": "x"},
        )
        # Unknown msg_type - silently ignored
        await z._zmq_handle_message(
            vehicle, {"msg_type": "unknown", "identifier": "me"}
        )
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_transition_runner_enqueues_message(self):
        """transition_runner() puts a TRANSITION message on the send queue."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        z._zmq_send_queue = asyncio.Queue()
        await z.transition_runner("other", "next_step")
        msg = z._zmq_send_queue.get_nowait()
        assert msg["msg_type"] == ZMQ_TYPE_TRANSITION
        assert msg["identifier"] == "other"
        assert msg["next_state"] == "next_step"
        assert msg["from"] == "me"
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_query_field_returns_value_on_reply(self):
        """query_field resolves immediately when a FIELD_CALLBACK arrives concurrently."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("requester", "127.0.0.1")
        z._zmq_send_queue = asyncio.Queue()
        vehicle = MockVehicle()

        async def _inject_reply():
            # Wait until query_field has registered its Event
            while (
                "responder" not in z._zmq_pending_fields
                or "altitude" not in z._zmq_pending_fields.get("responder", {})
            ):
                await asyncio.sleep(0.005)
            reply = {
                "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
                "from": "responder",
                "identifier": "requester",
                "field": "altitude",
                "value": 100.0,
            }
            await z._zmq_handle_message(vehicle, reply)

        asyncio.create_task(_inject_reply())
        result = await asyncio.wait_for(
            z.query_field("responder", "altitude", timeout=1.0), timeout=2.0
        )
        assert result == 100.0
        assert "altitude" not in z._zmq_pending_fields["responder"]
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    def test_expose_field_in_subclass_preserves_parent_initial_state(self):
        class Base(ZmqStateMachine):
            @state(name="start", first=True)
            async def start(self, vehicle):
                return None

        class Child(Base):
            @expose_field_zmq("battery")
            async def battery(self, vehicle):
                return 1

        cfg = Child.config
        assert cfg.initial_state == "start"
        assert "battery" in cfg.exposed_fields

    @pytest.mark.asyncio
    async def test_zmq_override_not_discarded_when_state_returns_none(self):
        """StateMachine.run respects ZMQ override even when state returns None (Bug #2 fix)."""
        visited = []

        class Z(ZmqStateMachine):
            @state(name="start", first=True)
            async def start(self, vehicle):
                # Simulate a ZMQ transition arriving while we're running
                self._next_state_overr = "end"
                self._override_next_state_transition = True
                return None  # would normally terminate — override should redirect

            @state(name="end")
            async def end(self, vehicle):
                visited.append("end")
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        # Patch out the ZMQ background loops so we don't need a live proxy
        z._zmq_recv_loop = lambda vehicle: asyncio.sleep(0)
        z._zmq_send_loop = lambda vehicle: asyncio.sleep(0)
        await z.run(MockVehicle())
        assert "end" in visited
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_times_out_without_telemetry_ticks(self):
        handler = ConnectionHandler(
            MockVehicle(),
            heartbeat_timeout=0.1,
            start_delay=0.0,
        )
        monitor = handler.start()
        disconnect_future = handler.get_disconnect_future()

        done, _ = await asyncio.wait(
            [disconnect_future], timeout=2.5, return_when=asyncio.FIRST_COMPLETED
        )
        assert disconnect_future in done
        assert isinstance(disconnect_future.exception(), HeartbeatLostError)

        handler.stop()
        if not monitor.done():
            monitor.cancel()
            with pytest.raises(asyncio.CancelledError):
                await monitor
        else:
            await monitor
