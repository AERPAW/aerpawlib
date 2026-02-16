"""Unit tests for aerpawlib v1 runner (BasicRunner, StateMachine, decorators)."""

import pytest

from aerpawlib.v1.runner import (
    BasicRunner,
    Runner,
    StateMachine,
    entrypoint,
    state,
    timed_state,
)
from aerpawlib.v1.vehicle import DummyVehicle


class TestBasicRunner:
    """BasicRunner and @entrypoint."""

    def test_entrypoint_decorator(self):
        class R(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                pass

        assert hasattr(R().run_mission, "_entrypoint")

    @pytest.mark.asyncio
    async def test_executes_entrypoint(self):
        ran = []

        class R(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                ran.append(1)

        await R().run(DummyVehicle())
        assert ran == [1]

    @pytest.mark.asyncio
    async def test_no_entrypoint_raises(self):
        class R(BasicRunner):
            async def run_mission(self, vehicle):
                pass

        with pytest.raises(Exception, match="No @entrypoint"):
            await R().run(DummyVehicle())

    @pytest.mark.asyncio
    async def test_receives_vehicle(self):
        received = []

        class R(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                received.append(vehicle)

        v = DummyVehicle()
        await R().run(v)
        assert received[0] is v


class TestStateMachine:
    """StateMachine and @state."""

    def test_state_decorator(self):
        class R(StateMachine):
            @state("start", first=True)
            async def start_state(self, vehicle):
                return None

        r = R()
        assert hasattr(r.start_state, "_is_state")
        assert r.start_state._state_name == "start"
        assert r.start_state._state_first is True

    @pytest.mark.asyncio
    async def test_single_state_exits(self):
        ran = []

        class R(StateMachine):
            @state("only", first=True)
            async def only_state(self, vehicle):
                ran.append(1)
                return None

        await R().run(DummyVehicle())
        assert ran == [1]

    @pytest.mark.asyncio
    async def test_transitions(self):
        ran = []

        class R(StateMachine):
            @state("first", first=True)
            async def first_state(self, vehicle):
                ran.append("first")
                return "second"

            @state("second")
            async def second_state(self, vehicle):
                ran.append("second")
                return "third"

            @state("third")
            async def third_state(self, vehicle):
                ran.append("third")
                return None

        await R().run(DummyVehicle())
        assert ran == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_loop_back(self):
        count = [0]

        class R(StateMachine):
            @state("loop", first=True)
            async def loop_state(self, vehicle):
                count[0] += 1
                return "loop" if count[0] < 3 else None

        await R().run(DummyVehicle())
        assert count[0] == 3


class TestTimedState:
    """@timed_state decorator."""

    def test_timed_state_marks(self):
        class R(StateMachine):
            @timed_state("wait", duration=1.0, first=True)
            async def wait_state(self, vehicle):
                return None

        assert R().wait_state._state_duration == 1.0

    @pytest.mark.asyncio
    async def test_timed_state_waits(self):
        import time

        class R(StateMachine):
            @timed_state("wait", duration=0.3, first=True)
            async def wait_state(self, vehicle):
                return None

        start = time.time()
        await R().run(DummyVehicle())
        assert time.time() - start >= 0.25


class TestRunnerInit:
    """Runner.initialize_args and cleanup."""

    def test_initialize_args_default(self):
        Runner().initialize_args(["--foo"])

    def test_cleanup_default(self):
        Runner().cleanup()

    def test_custom_initialize_args(self):
        args = []

        class R(BasicRunner):
            def initialize_args(self, a):
                args.extend(a)

            @entrypoint
            async def run_mission(self, vehicle):
                pass

        R().initialize_args(["--x", "1"])
        assert args == ["--x", "1"]
