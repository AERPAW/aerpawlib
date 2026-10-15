"""Unit tests for aerpawlib v2 BasicRunner, StateMachine, and ZmqStateMachine."""

import asyncio

import pytest

from aerpawlib.v2.constants import (
    ZMQ_TYPE_FIELD_CALLBACK,
    ZMQ_TYPE_FIELD_REQUEST,
    ZMQ_TYPE_TRANSITION,
)
from aerpawlib.v2.exceptions import (
    HeartbeatLostError,
    MultipleInitialStatesError,
    NoEntrypointError,
    NoInitialStateError,
    RunnerError,
)
from aerpawlib.v2.runner import (
    BasicRunner,
    StateMachine,
    ZmqStateMachine,
    at_init,
    background,
    entrypoint,
    expose_field_zmq,
    expose_zmq,
    state,
    timed_state,
)
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
        # Py <3.12 wraps __set_name__ failures in RuntimeError; 3.12+ raises
        # RunnerError.
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
                return

        await SM().run(MockVehicle())
        assert order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_identity_transition_idles_instead_of_spinning(self):
        import time

        loops = []

        class SM(StateMachine):
            @state(name="wait", first=True)
            async def wait(self, vehicle):
                loops.append(1)
                if len(loops) >= 3:
                    return None
                return "wait"

        t0 = time.monotonic()
        await SM().run(MockVehicle())
        elapsed = time.monotonic() - t0
        assert loops == [1, 1, 1]
        assert elapsed >= 0.15

    @pytest.mark.asyncio
    async def test_timed_state_duration(self):
        order = []

        class SM(StateMachine):
            @timed_state(name="t", duration=0.1, first=True)
            async def t(self, vehicle):
                order.append("t")
                return

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
                return

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
                return

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
                return

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
                return

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
    @pytest.fixture(autouse=True)
    def mock_proxy_reachable(self, monkeypatch):
        import aerpawlib.v2.runner.impl

        monkeypatch.setattr(aerpawlib.v2.runner.impl, "check_zmq_proxy_reachable", lambda *args, **kwargs: True)

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
        # Send queue is created in run() when an event loop is running.
        assert z._zmq_send_queue is None
        assert z._zmq_received_fields == {}
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
        assert any(spec.name == "internal" and spec.method_name == "s" for spec in cfg.states)
        assert cfg.exposed_states["remote"] == "internal"

    def test_state_then_expose_zmq_registers_exposed_state(self):
        class Z(ZmqStateMachine):
            @state(name="internal", first=True)
            @expose_zmq("remote")
            async def s(self, vehicle):
                return None

        cfg = Z.config
        assert cfg.initial_state == "internal"
        assert any(spec.name == "internal" and spec.method_name == "s" for spec in cfg.states)
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


class TestDisconnectWatch:
    @pytest.fixture(autouse=True)
    def mock_proxy_reachable(self, monkeypatch):
        import aerpawlib.v2.runner.impl

        monkeypatch.setattr(aerpawlib.v2.runner.impl, "check_zmq_proxy_reachable", lambda *args, **kwargs: True)

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
            "next_state": "a",
        }
        await z._zmq_handle_message(MockVehicle(), msg)
        assert z._override_next_state_transition is True
        assert z._next_state_overr == "a"
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_transitions_queued(self):
        """Test that multiple TRANSITION messages are queued rather than overwritten."""

        class Z(ZmqStateMachine):
            @state(name="a", first=True)
            async def a(self, vehicle):
                return None

            @state(name="state_one")
            async def state_one(self, vehicle):
                return None

            @state(name="state_two")
            async def state_two(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        msg1 = {
            "msg_type": ZMQ_TYPE_TRANSITION,
            "from": "other",
            "identifier": "me",
            "next_state": "state_one",
        }
        msg2 = {
            "msg_type": ZMQ_TYPE_TRANSITION,
            "from": "other",
            "identifier": "me",
            "next_state": "state_two",
        }
        await z._zmq_handle_message(MockVehicle(), msg1)
        await z._zmq_handle_message(MockVehicle(), msg2)

        assert len(z._next_state_overrides) == 2
        assert z._next_state_overrides[0] == "state_one"
        assert z._next_state_overrides[1] == "state_two"

        # Test backward-compatible property getters
        assert z._override_next_state_transition is True
        assert z._next_state_overr == "state_one"

        # Consuming the first override
        z._override_next_state_transition = False
        assert len(z._next_state_overrides) == 1
        assert z._next_state_overr == "state_two"

        # Consuming the second override
        z._override_next_state_transition = False
        assert len(z._next_state_overrides) == 0
        assert z._override_next_state_transition is False
        assert z._next_state_overr == ""

        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_unknown_transition_is_ignored(self):
        class Z(ZmqStateMachine):
            @state(name="a", first=True)
            async def a(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        await z._zmq_handle_message(
            MockVehicle(),
            {
                "msg_type": ZMQ_TYPE_TRANSITION,
                "from": "other",
                "identifier": "me",
                "next_state": "does_not_exist",
            },
        )
        assert z._next_state_overrides == []

    @pytest.mark.asyncio
    async def test_expose_zmq_alias_maps_to_internal_state(self):
        class Z(ZmqStateMachine):
            @state(name="idle", first=True)
            async def idle(self, vehicle):
                return None

            @expose_zmq("remote_takeoff")
            @state(name="takeoff")
            async def takeoff(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        await z._zmq_handle_message(
            MockVehicle(),
            {
                "msg_type": ZMQ_TYPE_TRANSITION,
                "from": "other",
                "identifier": "me",
                "next_state": "remote_takeoff",
            },
        )
        assert z._next_state_overr == "takeoff"

    @pytest.mark.asyncio
    async def test_handle_field_callback_sets_value_and_signals_event(self):
        """FIELD_CALLBACK with req_id completes a pending query."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        event = asyncio.Event()
        z._zmq_pending_queries["req-1"] = {"event": event, "value": None, "error": None}

        msg = {
            "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
            "from": "sender",
            "identifier": "me",
            "field": "myfield",
            "value": 42,
            "req_id": "req-1",
        }
        await z._zmq_handle_message(MockVehicle(), msg)
        assert z._zmq_pending_queries["req-1"]["value"] == 42
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_unsolicited_field_callback_stored_without_error(self):
        """An unsolicited FIELD_CALLBACK (no pending
        Event) is stored without raising."""

        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        # No entry in _zmq_received_fields for "stranger"

        msg = {
            "msg_type": ZMQ_TYPE_FIELD_CALLBACK,
            "from": "stranger",
            "identifier": "me",
            "field": "data",
            "value": "hello",
        }
        await z._zmq_handle_message(MockVehicle(), msg)
        assert z._zmq_received_fields["stranger"]["data"] == "hello"
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
            vehicle,
            {"msg_type": ZMQ_TYPE_TRANSITION, "identifier": "me"},
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
            vehicle,
            {"msg_type": "unknown", "identifier": "me"},
        )
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_transition_runner_raises_if_not_started(self):
        class Z(ZmqStateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        with pytest.raises(RuntimeError, match="ZMQ not initialized"):
            await z.transition_runner("other", "next_step")

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
    async def test_zmq_override_discarded_when_state_returns_none(self):
        """A state returning None ends the machine and drops queued overrides.

        This used to assert the opposite (the queued override ran after the
        terminal return). That is unsafe: a stale queued transition such as
        ``takeoff`` would run after a final ``land`` state returned None and
        put the vehicle back in the air. Queued overrides are still honored
        after a state that returns a next-state name (see
        test_queued_overrides_still_run_after_non_terminal_state).
        """
        visited = []

        class Z(ZmqStateMachine):
            @state(name="start", first=True)
            async def start(self, vehicle):
                # Simulate a ZMQ transition arriving while we're running
                self._next_state_overr = "end"
                self._override_next_state_transition = True
                return  # terminal: the queued override must not run

            @state(name="end")
            async def end(self, vehicle):
                visited.append("end")
                return

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")

        async def _noop() -> None:
            return None

        z._zmq_transport.start = _noop  # type: ignore[method-assign]
        z._zmq_transport.stop = _noop  # type: ignore[method-assign]
        await z.run(MockVehicle())
        assert visited == []
        assert z._next_state_overrides == []
        if z._zmq_context is not None:
            z._zmq_context.destroy(linger=0)

    @pytest.mark.asyncio
    async def test_times_out_without_telemetry_ticks(self):
        vehicle = MockVehicle()
        disconnect_future = vehicle.watch_disconnect(0.1)

        done, _ = await asyncio.wait(
            [disconnect_future],
            timeout=2.5,
            return_when=asyncio.FIRST_COMPLETED,
        )
        assert disconnect_future in done
        assert isinstance(disconnect_future.exception(), HeartbeatLostError)


def _unwrap_set_name_error(err):
    """Py <3.12 wraps __set_name__ failures in RuntimeError."""
    return err.__cause__ if isinstance(err, RuntimeError) and err.__cause__ else err


def _other_tasks():
    return [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]


class TestTimedStateTaskLifecycle:
    """@timed_state body task must never outlive the state."""

    @pytest.mark.asyncio
    async def test_cancel_during_looping_timed_state_stops_body(self):
        ticks = []
        cleanups = []
        release = asyncio.Event()

        class SM(StateMachine):
            @timed_state(name="t", duration=5.0, loop=True, first=True)
            async def t(self, vehicle):
                ticks.append("enter")
                await release.wait()
                ticks.append("body_finished")

            def cleanup(self):
                cleanups.append(1)

        sm = SM()
        run = asyncio.create_task(sm.run(MockVehicle()))
        await asyncio.sleep(0.05)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert _other_tasks() == []
        assert cleanups == [1]
        release.set()
        await asyncio.sleep(0.05)
        assert ticks == ["enter"]

    @pytest.mark.asyncio
    async def test_unexpected_disarm_during_timed_state_stops_body(self):
        from aerpawlib.v2.exceptions import UnexpectedDisarmError

        ticks = []
        release = asyncio.Event()
        vehicle = MockVehicle()
        vehicle._unexpected_disarm_event = asyncio.Event()

        class SM(StateMachine):
            @timed_state(name="t", duration=5.0, loop=True, first=True)
            async def t(self, vehicle):
                ticks.append("enter")
                await release.wait()
                ticks.append("body_finished")

        run = asyncio.create_task(SM().run(vehicle))
        await asyncio.sleep(0.05)
        vehicle._unexpected_disarm_event.set()
        with pytest.raises(UnexpectedDisarmError):
            await asyncio.wait_for(run, timeout=1.0)
        assert _other_tasks() == []
        release.set()
        await asyncio.sleep(0.05)
        assert ticks == ["enter"]

    @pytest.mark.asyncio
    async def test_body_exception_surfaces_before_duration(self):
        import time

        class SM(StateMachine):
            @timed_state(name="t", duration=5.0, first=True)
            async def t(self, vehicle):
                raise ValueError("boom")

        t0 = time.monotonic()
        with pytest.raises(ValueError, match="boom"):
            await SM().run(MockVehicle())
        assert time.monotonic() - t0 < 1.0

    @pytest.mark.asyncio
    async def test_non_loop_body_still_holds_for_full_duration(self):
        import time

        order = []

        class SM(StateMachine):
            @timed_state(name="t", duration=0.2, first=True)
            async def t(self, vehicle):
                order.append("t")
                return "u"

            @state(name="u")
            async def u(self, vehicle):
                order.append("u")

        t0 = time.monotonic()
        await SM().run(MockVehicle())
        assert order == ["t", "u"]
        assert time.monotonic() - t0 >= 0.2

    @pytest.mark.parametrize("duration", [0, -1.0, float("nan"), float("inf")])
    def test_invalid_duration_rejected_at_decoration(self, duration):
        with pytest.raises(RunnerError, match="duration"):
            timed_state(name="t", duration=duration)


class TestStateMachineRegressions:
    @pytest.mark.asyncio
    async def test_disarm_set_as_final_state_returns_raises(self):
        """Disarm event set while the state is finishing must not report success."""
        from aerpawlib.v2.exceptions import UnexpectedDisarmError

        vehicle = MockVehicle()
        vehicle._unexpected_disarm_event = asyncio.Event()

        class SM(StateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                vehicle._unexpected_disarm_event.set()
                return None

        with pytest.raises(UnexpectedDisarmError):
            await SM().run(vehicle)

    @pytest.mark.asyncio
    async def test_cancel_with_disarm_guard_unwinds_state_before_cleanup(self):
        order = []
        vehicle = MockVehicle()
        vehicle._unexpected_disarm_event = asyncio.Event()

        class SM(StateMachine):
            @state(name="s", first=True)
            async def s(self, vehicle):
                try:
                    await asyncio.sleep(30)
                finally:
                    await asyncio.sleep(0)
                    order.append("state_unwound")

            def cleanup(self):
                order.append("cleanup")

        run = asyncio.create_task(SM().run(vehicle))
        await asyncio.sleep(0.05)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert order == ["state_unwound", "cleanup"]
        assert _other_tasks() == []

    @pytest.mark.asyncio
    async def test_redecorated_inherited_background_and_at_init_registered_once(self):
        init_calls = []
        bg_calls = []

        class Base(StateMachine):
            @at_init
            async def setup(self, vehicle):
                init_calls.append("base")

            @background
            async def monitor(self, vehicle):
                bg_calls.append("base")
                await asyncio.sleep(10)

            @state(name="s", first=True)
            async def s(self, vehicle):
                await asyncio.sleep(0.02)

        class Child(Base):
            @at_init
            async def setup(self, vehicle):
                init_calls.append("child")

            @background
            async def monitor(self, vehicle):
                bg_calls.append("child")
                await asyncio.sleep(10)

        assert Child.config.at_init == ["setup"]
        assert Child.config.backgrounds == ["monitor"]
        assert Base.config.at_init == ["setup"]
        child = Child()
        await child.run(MockVehicle())
        assert init_calls == ["child"]
        assert bg_calls == ["child"]
        assert len(child._background_futures) == 1

    @pytest.mark.asyncio
    async def test_subclass_override_of_state_replaces_inherited_spec(self):
        ran = []

        class Base(StateMachine):
            @state(name="go", first=True)
            async def go(self, vehicle):
                ran.append("base")

        class Child(Base):
            @state(name="go", first=True)
            async def go(self, vehicle):
                ran.append("child")

        assert [(s.name, s.method_name) for s in Child.config.states] == [("go", "go")]
        assert Child.config.initial_state == "go"
        await Child().run(MockVehicle())
        assert ran == ["child"]

    def test_duplicate_state_names_raise(self):
        with pytest.raises((RuntimeError, RunnerError)) as excinfo:

            class SM(StateMachine):
                @state(name="go", first=True)
                async def alpha(self, vehicle):
                    return None

                @state(name="go")
                async def beta(self, vehicle):
                    return None

        inner = _unwrap_set_name_error(excinfo.value)
        assert isinstance(inner, RunnerError)
        assert "Duplicate state name 'go'" in str(inner)

    @pytest.mark.asyncio
    async def test_override_queued_during_idle_sleep_is_honored(self):
        visits = []

        class SM(StateMachine):
            @state(name="leg", first=True)
            async def leg(self, vehicle):
                visits.append("leg")
                if len(visits) == 1:
                    asyncio.get_running_loop().call_later(
                        0.05,
                        self._next_state_overrides.append,
                        "land",
                    )
                return "leg"

            @state(name="land")
            async def land(self, vehicle):
                visits.append("land")

        await asyncio.wait_for(SM().run(MockVehicle()), timeout=2.0)
        assert visits == ["leg", "land"]

    @pytest.mark.asyncio
    async def test_background_exceeding_max_retries_fails_run(self, monkeypatch):
        real_sleep = asyncio.sleep

        async def fast_sleep(delay, *args, **kwargs):
            # Collapse the retry backoff (>= 0.5 s) so the cap is reached quickly.
            return await real_sleep(0 if delay >= 0.5 else delay, *args, **kwargs)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)
        attempts = []
        cleanups = []

        class SM(StateMachine):
            @background
            async def monitor(self, vehicle):
                attempts.append(1)
                raise OSError("log closed")

            @state(name="s", first=True)
            async def s(self, vehicle):
                await asyncio.Event().wait()  # long goto

            def cleanup(self):
                cleanups.append(1)

        with pytest.raises(RunnerError, match="exceeded max retries") as excinfo:
            await asyncio.wait_for(SM().run(MockVehicle()), timeout=5.0)
        assert isinstance(excinfo.value.__cause__, OSError)
        assert len(attempts) == 10
        assert cleanups == [1]
        assert _other_tasks() == []

    @pytest.mark.asyncio
    async def test_background_running_before_first_state(self):
        seen = []
        bg_started = []

        class SM(StateMachine):
            @background
            async def monitor(self, vehicle):
                bg_started.append(1)
                await asyncio.sleep(10)

            @state(name="s", first=True)
            async def s(self, vehicle):
                # Synchronous prefix of the first state, before any await.
                seen.append(bool(bg_started))

        await SM().run(MockVehicle())
        assert seen == [True]

    @pytest.mark.asyncio
    async def test_at_init_hooks_run_concurrently(self):
        order = []
        ready = asyncio.Event()

        class SM(StateMachine):
            @at_init
            async def a(self, vehicle):
                order.append("a_start")
                await ready.wait()
                order.append("a_done")

            @at_init
            async def b(self, vehicle):
                order.append("b")
                ready.set()

            @state(name="s", first=True)
            async def s(self, vehicle):
                order.append("s")

        await asyncio.wait_for(SM().run(MockVehicle()), timeout=1.0)
        assert order == ["a_start", "b", "a_done", "s"]

    @pytest.mark.asyncio
    async def test_at_init_failure_cancels_sibling_and_runs_cleanup(self):
        sibling = []
        cleanups = []

        class SM(StateMachine):
            @at_init
            async def a(self, vehicle):
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    sibling.append("cancelled")
                    raise

            @at_init
            async def b(self, vehicle):
                raise ValueError("init failed")

            @state(name="s", first=True)
            async def s(self, vehicle):
                raise AssertionError("first state must not run")

            def cleanup(self):
                cleanups.append(1)

        with pytest.raises(ValueError, match="init failed"):
            await SM().run(MockVehicle())
        assert sibling == ["cancelled"]
        assert cleanups == [1]
        assert _other_tasks() == []


class TestZmqRegressions:
    @pytest.fixture(autouse=True)
    def mock_proxy_reachable(self, monkeypatch):
        import aerpawlib.v2.runner.impl

        monkeypatch.setattr(aerpawlib.v2.runner.impl, "check_zmq_proxy_reachable", lambda *args, **kwargs: True)

    @staticmethod
    def _offline(z):
        """Bind ZMQ without starting the real transport."""

        async def _noop() -> None:
            return None

        z._initialize_zmq_bindings("me", "127.0.0.1")
        z._zmq_transport.start = _noop  # type: ignore[method-assign]
        z._zmq_transport.stop = _noop  # type: ignore[method-assign]
        return z

    @pytest.mark.asyncio
    async def test_terminal_state_drops_queued_takeoff(self):
        cmds = []

        class Z(ZmqStateMachine):
            @state(name="idle", first=True)
            async def idle(self, vehicle):
                cmds.append("idle")
                for name in ("takeoff", "land"):
                    await self._zmq_handle_message(
                        vehicle,
                        {"msg_type": ZMQ_TYPE_TRANSITION, "from": "x", "identifier": "me", "next_state": name},
                    )
                return None

            @state(name="takeoff")
            async def takeoff(self, vehicle):
                cmds.append("takeoff")
                return "land"

            @state(name="land")
            async def land(self, vehicle):
                cmds.append("land")

        z = self._offline(Z())
        await z.run(MockVehicle())
        assert cmds == ["idle"]
        assert z._next_state_overrides == []

    @pytest.mark.asyncio
    async def test_queued_overrides_still_run_after_non_terminal_state(self):
        """Paired callbacks queued during one wait state must both run (orbit coordinator)."""
        visits = []

        class Z(ZmqStateMachine):
            @state(name="wait", first=True)
            async def wait(self, vehicle):
                visits.append("wait")
                if visits.count("wait") == 1:
                    self._next_state_overrides.extend(["cb_one", "cb_two"])
                    return "wait"
                return None

            @state(name="cb_one")
            async def cb_one(self, vehicle):
                visits.append("cb_one")
                return "wait"

            @state(name="cb_two")
            async def cb_two(self, vehicle):
                visits.append("cb_two")
                return "wait"

        z = self._offline(Z())
        await asyncio.wait_for(z.run(MockVehicle()), timeout=2.0)
        assert visits == ["wait", "cb_one", "cb_two", "wait"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [["a"], {"a": 1}, 5])
    async def test_non_string_next_state_is_ignored(self, bad):
        class Z(ZmqStateMachine):
            @state(name="a", first=True)
            async def a(self, vehicle):
                return None

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        await z._zmq_handle_message(
            MockVehicle(),
            {"msg_type": ZMQ_TYPE_TRANSITION, "from": "x", "identifier": "me", "next_state": bad},
        )
        assert z._next_state_overrides == []

    @pytest.mark.asyncio
    async def test_unknown_field_request_replies_with_error(self):
        class Z(ZmqStateMachine):
            @state(name="a", first=True)
            async def a(self, vehicle):
                return None

            @expose_field_zmq("position")
            async def position(self, vehicle):
                return 1

        replies = []

        async def _record(identifier, field, value, req_id=None, error=None):
            replies.append((field, value, req_id, error))

        z = Z()
        z._initialize_zmq_bindings("me", "127.0.0.1")
        z._zmq_send_reply = _record  # type: ignore[method-assign]
        vehicle = MockVehicle()
        for field in ("no_such_field", "position"):
            await z._zmq_handle_message(
                vehicle,
                {"msg_type": ZMQ_TYPE_FIELD_REQUEST, "from": "peer", "identifier": "me", "field": field, "req_id": "r1"},
            )
        assert replies[0][0] == "no_such_field"
        assert replies[0][1] is None
        assert "Unknown field" in replies[0][3]
        assert replies[1] == ("position", 1, "r1", None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("order", ["expose_outer", "state_outer"])
    async def test_expose_zmq_state_named_run(self, order):
        cmds = []

        if order == "expose_outer":

            class Z(ZmqStateMachine):
                @expose_zmq("go")
                @state(name="only", first=True)
                async def run(self, vehicle):
                    cmds.append("state_run")

        else:

            class Z(ZmqStateMachine):
                @state(name="only", first=True)
                @expose_zmq("go")
                async def run(self, vehicle):
                    cmds.append("state_run")

        assert Z.config.exposed_states == {"go": "only"}
        z = self._offline(Z())
        await z.run(MockVehicle())
        assert cmds == ["state_run"]
