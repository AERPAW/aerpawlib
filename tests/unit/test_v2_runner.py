"""
Unit tests for v2 Runner classes.

Tests BasicRunner, StateMachine, state decorators, etc.
"""

import pytest
import asyncio
from aerpawlib.v2.runner import (
    BasicRunner,
    StateMachine,
    entrypoint,
    state,
    timed_state,
    background,
    at_init,
    DecoratorType,
    StateType,
)


class MockVehicle:
    """Mock vehicle for testing runners without SITL."""

    def __init__(self):
        self.connected = True
        self.armed = False

    def close(self):
        pass


class TestBasicRunner:
    """Tests for BasicRunner class."""

    def test_entrypoint_decorator_creates_descriptor(self):
        """Test @entrypoint creates a MethodDescriptor."""

        class TestRunner(BasicRunner):
            @entrypoint
            async def my_entry(self, vehicle):
                pass

        runner = TestRunner()
        # The descriptor should be accessible
        assert hasattr(TestRunner, "_aerpaw_descriptors")

    @pytest.mark.asyncio
    async def test_basic_runner_executes_entrypoint(self):
        """Test BasicRunner executes the entrypoint function."""
        executed = []

        class TestRunner(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                executed.append("ran")

        runner = TestRunner()
        vehicle = MockVehicle()
        await runner.run(vehicle)

        assert executed == ["ran"]

    @pytest.mark.asyncio
    async def test_basic_runner_receives_vehicle(self):
        """Test entrypoint receives the vehicle object."""
        received_vehicle = []

        class TestRunner(BasicRunner):
            @entrypoint
            async def run_mission(self, vehicle):
                received_vehicle.append(vehicle)

        runner = TestRunner()
        vehicle = MockVehicle()
        await runner.run(vehicle)

        assert received_vehicle[0] is vehicle


class TestStateMachine:
    """Tests for StateMachine runner."""

    def test_state_decorator_config(self):
        """Test @state creates proper StateConfig."""

        class TestRunner(StateMachine):
            @state("start", first=True)
            async def start_state(self, vehicle):
                return None

        # Check descriptor was registered
        assert hasattr(TestRunner, "_aerpaw_descriptors")
        descriptors = TestRunner._aerpaw_descriptors
        state_desc = [
            d for d in descriptors if d.decorator_type == DecoratorType.STATE
        ][0]
        assert state_desc.state_config.name == "start"
        assert state_desc.state_config.is_initial is True

    def test_state_decorator_empty_name_raises(self):
        """Test @state with empty name raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):

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
        vehicle = MockVehicle()
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
        vehicle = MockVehicle()
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
                    return "loop"
                return None  # Exit after 3 iterations

        runner = TestRunner()
        vehicle = MockVehicle()
        await runner.run(vehicle)

        assert counter[0] == 3


class TestTimedState:
    """Tests for timed_state decorator."""

    def test_timed_state_config(self):
        """Test @timed_state creates proper StateConfig."""

        class TestRunner(StateMachine):
            @timed_state("wait", duration=5.0, first=True)
            async def wait_state(self, vehicle):
                return None

        descriptors = TestRunner._aerpaw_descriptors
        state_desc = [
            d for d in descriptors if d.decorator_type == DecoratorType.STATE
        ][0]
        assert state_desc.state_config.name == "wait"
        assert state_desc.state_config.duration == 5.0
        assert state_desc.state_config.state_type == StateType.TIMED

    def test_timed_state_invalid_duration_raises(self):
        """Test @timed_state with invalid duration raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):

            @timed_state("test", duration=0)
            async def bad_state(self, vehicle):
                return None

    @pytest.mark.asyncio
    async def test_timed_state_waits(self):
        """Test timed_state waits for duration."""
        import time

        class TestRunner(StateMachine):
            @timed_state("wait", duration=0.5, first=True)
            async def wait_state(self, vehicle):
                return None

        runner = TestRunner()
        vehicle = MockVehicle()

        start = time.time()
        await runner.run(vehicle)
        elapsed = time.time() - start

        assert elapsed >= 0.4
        assert elapsed < 1.0


class TestBackgroundDecorator:
    """Tests for @background decorator."""

    def test_background_decorator_type(self):
        """Test @background creates correct descriptor type."""

        class TestRunner(StateMachine):
            @background
            async def log_stuff(self, vehicle):
                await asyncio.sleep(1)

            @state("main", first=True)
            async def main_state(self, vehicle):
                return None

        descriptors = TestRunner._aerpaw_descriptors
        bg_descs = [
            d
            for d in descriptors
            if d.decorator_type == DecoratorType.BACKGROUND
        ]
        assert len(bg_descs) == 1


class TestAtInitDecorator:
    """Tests for @at_init decorator."""

    def test_at_init_decorator_type(self):
        """Test @at_init creates correct descriptor type."""

        class TestRunner(StateMachine):
            @at_init
            async def setup(self, vehicle):
                pass

            @state("main", first=True)
            async def main_state(self, vehicle):
                return None

        descriptors = TestRunner._aerpaw_descriptors
        init_descs = [
            d for d in descriptors if d.decorator_type == DecoratorType.INIT
        ]
        assert len(init_descs) == 1


class TestRunnerInitializeArgs:
    """Tests for Runner argument initialization."""

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
