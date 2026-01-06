"""
Unit tests for Runner classes.

Tests BasicRunner, StateMachine, state decorators, etc.
"""
import pytest
from aerpawlib.v1.runner import (
    Runner,
    BasicRunner,
    StateMachine,
    entrypoint,
    state,
    timed_state,
)
from aerpawlib.v1.vehicle import DummyVehicle


class TestBasicRunner:
    """Tests for BasicRunner class."""

    def test_entrypoint_decorator(self):
        """Test @entrypoint decorator marks function."""

        class TestRunner(BasicRunner):
            @entrypoint
            async def my_entry(self, vehicle):
                pass

        runner = TestRunner()
        assert hasattr(runner.my_entry, '_entrypoint')
        assert runner.my_entry._entrypoint is True

    @pytest.mark.asyncio
    async def test_basic_runner_executes_entrypoint(self):
        """Test BasicRunner executes the entrypoint function."""
        executed = []

        class TestRunner(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                executed.append("ran")

        runner = TestRunner()
        vehicle = DummyVehicle()
        await runner.run(vehicle)

        assert executed == ["ran"]

    @pytest.mark.asyncio
    async def test_basic_runner_no_entrypoint_raises(self):
        """Test BasicRunner without @entrypoint raises exception."""

        class TestRunner(BasicRunner):
            async def some_method(self, vehicle):
                pass

        runner = TestRunner()
        vehicle = DummyVehicle()

        with pytest.raises(Exception, match="No @entrypoint declared"):
            await runner.run(vehicle)

    @pytest.mark.asyncio
    async def test_basic_runner_receives_vehicle(self):
        """Test entrypoint receives the vehicle object."""
        received_vehicle = []

        class TestRunner(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                received_vehicle.append(vehicle)

        runner = TestRunner()
        vehicle = DummyVehicle()
        await runner.run(vehicle)

        assert received_vehicle[0] is vehicle


class TestStateMachine:
    """Tests for StateMachine runner."""

    def test_state_decorator(self):
        """Test @state decorator marks function."""

        class TestRunner(StateMachine):
            @state("start", first=True)
            async def start_state(self, vehicle):
                return None

        runner = TestRunner()
        assert hasattr(runner.start_state, '_is_state')
        assert runner.start_state._state_name == "start"
        assert runner.start_state._state_first is True

    def test_state_decorator_empty_name_raises(self):
        """Test @state with empty name raises exception."""
        with pytest.raises(Exception, match="state name can't be"):
            @state("")
            async def bad_state(self, vehicle):
                return None

    @pytest.mark.asyncio
    async def test_state_machine_single_state(self):
        """Test StateMachine with single state that exits."""
        executed = []

        class TestRunner(StateMachine):
            @state("only", first=True)
            async def only_state(self, vehicle):
                executed.append("only")
                return None  # None exits

        runner = TestRunner()
        vehicle = DummyVehicle()
        await runner.run(vehicle)

        assert executed == ["only"]

    @pytest.mark.asyncio
    async def test_state_machine_transitions(self):
        """Test StateMachine transitions between states."""
        executed = []

        class TestRunner(StateMachine):
            @state("first", first=True)
            async def first_state(self, vehicle):
                executed.append("first")
                return "second"

            @state("second")
            async def second_state(self, vehicle):
                executed.append("second")
                return "third"

            @state("third")
            async def third_state(self, vehicle):
                executed.append("third")
                return None  # Exit

        runner = TestRunner()
        vehicle = DummyVehicle()
        await runner.run(vehicle)

        assert executed == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_state_machine_loop(self):
        """Test StateMachine can loop back to previous states."""
        counter = [0]

        class TestRunner(StateMachine):
            @state("loop", first=True)
            async def loop_state(self, vehicle):
                counter[0] += 1
                if counter[0] < 3:
                    return "loop"  # Loop back
                return None  # Exit after 3 iterations

        runner = TestRunner()
        vehicle = DummyVehicle()
        await runner.run(vehicle)

        assert counter[0] == 3


class TestTimedState:
    """Tests for timed_state decorator."""

    def test_timed_state_decorator(self):
        """Test @timed_state decorator marks function."""

        class TestRunner(StateMachine):
            @timed_state("wait", duration=1.0, first=True)
            async def wait_state(self, vehicle):
                return None

        runner = TestRunner()
        assert hasattr(runner.wait_state, '_is_state')
        assert runner.wait_state._state_duration == 1.0

    @pytest.mark.asyncio
    async def test_timed_state_waits(self):
        """Test timed_state waits for duration."""
        import time

        class TestRunner(StateMachine):
            @timed_state("wait", duration=0.5, first=True)
            async def wait_state(self, vehicle):
                return None

        runner = TestRunner()
        vehicle = DummyVehicle()

        start = time.time()
        await runner.run(vehicle)
        elapsed = time.time() - start

        # Should have waited approximately 0.5 seconds
        assert elapsed >= 0.4
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_timed_state_loop(self):
        """Test timed_state with loop=True calls repeatedly."""
        call_count = [0]

        class TestRunner(StateMachine):
            @timed_state("loop", duration=0.3, loop=True, first=True)
            async def loop_state(self, vehicle):
                call_count[0] += 1
                return None

        runner = TestRunner()
        vehicle = DummyVehicle()
        await runner.run(vehicle)

        # With loop=True and 0.3s duration, should call multiple times
        assert call_count[0] > 1


class TestRunnerInitializeArgs:
    """Tests for Runner argument initialization."""

    def test_initialize_args_default(self):
        """Test default initialize_args does nothing."""
        runner = Runner()
        # Should not raise
        runner.initialize_args(["--some", "args"])

    def test_initialize_args_custom(self):
        """Test custom initialize_args receives arguments."""
        received_args = []

        class TestRunner(BasicRunner):
            def initialize_args(self, args):
                received_args.extend(args)

            @entrypoint
            async def run_mission(self, vehicle):
                pass

        runner = TestRunner()
        runner.initialize_args(["--custom", "value"])

        assert received_args == ["--custom", "value"]


class TestRunnerCleanup:
    """Tests for Runner cleanup."""

    def test_cleanup_default(self):
        """Test default cleanup does nothing."""
        runner = Runner()
        # Should not raise
        runner.cleanup()

    def test_cleanup_custom(self):
        """Test custom cleanup is called."""
        cleaned_up = []

        class TestRunner(BasicRunner):
            def cleanup(self):
                cleaned_up.append("cleaned")

            @entrypoint
            async def run_mission(self, vehicle):
                pass

        runner = TestRunner()
        runner.cleanup()

        assert cleaned_up == ["cleaned"]

