import asyncio
import logging
import types

import pytest

from aerpawlib import __main__ as cli_main
from aerpawlib.v1.exceptions import HeartbeatLostError


@pytest.fixture(autouse=True)
def _set_test_logger():
    cli_main.logger = logging.getLogger("aerpawlib.test")


def _build_fake_api_module():
    class Runner:
        pass

    class BasicRunner(Runner):
        pass

    class StateMachine(Runner):
        pass

    class ZmqStateMachine(StateMachine):
        pass

    return types.SimpleNamespace(
        Runner=Runner,
        BasicRunner=BasicRunner,
        StateMachine=StateMachine,
        ZmqStateMachine=ZmqStateMachine,
    )


def test_discover_runner_accepts_direct_subclass_only():
    api = _build_fake_api_module()
    script = types.ModuleType("fake_script")

    class Mission(api.StateMachine):
        pass

    script.Mission = Mission

    runner, is_zmq = cli_main.discover_runner(api, script)
    assert isinstance(runner, Mission)
    assert is_zmq is False


def test_discover_runner_rejects_indirect_subclass():
    api = _build_fake_api_module()
    script = types.ModuleType("fake_script")

    class Base(api.StateMachine):
        pass

    class Mission(Base):
        pass

    script.Mission = Mission

    with pytest.raises(Exception, match="No Runner class found"):
        cli_main.discover_runner(api, script)


def test_discover_runner_raises_for_multiple_direct_subclasses():
    api = _build_fake_api_module()
    script = types.ModuleType("fake_script")

    class MissionA(api.StateMachine):
        pass

    class MissionB(api.BasicRunner):
        pass

    script.MissionA = MissionA
    script.MissionB = MissionB

    with pytest.raises(Exception, match="only define one runner"):
        cli_main.discover_runner(api, script)


@pytest.mark.asyncio
async def test_run_runner_without_disconnect_future():
    class Runner:
        def __init__(self):
            self.called = False

        async def run(self, vehicle):
            self.called = True

    runner = Runner()
    await cli_main._run_runner_with_disconnect_guard(
        runner=runner,
        vehicle=object(),
    )

    assert runner.called


@pytest.mark.asyncio
async def test_run_runner_plain_run_races_disconnect_future():
    cancelled = []

    class Runner:
        async def run(self, vehicle):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

    disconnect_future = asyncio.get_running_loop().create_future()

    async def trigger_disconnect():
        await asyncio.sleep(0.02)
        disconnect_future.set_exception(RuntimeError("lost"))

    with pytest.raises(RuntimeError, match="lost"):
        await asyncio.gather(
            cli_main._run_runner_with_disconnect_guard(
                runner=Runner(),
                vehicle=object(),
                disconnect_future=disconnect_future,
            ),
            trigger_disconnect(),
        )

    assert cancelled


@pytest.mark.asyncio
async def test_v1_connection_loss_waiter_raises_on_disconnect_timeout():
    class FakeVehicle:
        def __init__(self):
            self.connected = False
            self._closed = False
            self._connection_error = None

    with pytest.raises(HeartbeatLostError):
        await cli_main._wait_for_v1_connection_loss(
            vehicle=FakeVehicle(),
            heartbeat_timeout=0.01,
            heartbeat_error_cls=HeartbeatLostError,
        )


@pytest.mark.asyncio
async def test_run_runner_disconnect_guard_raises_disconnect_error():
    class Runner:
        async def run(self, vehicle):
            await asyncio.sleep(10)

    disconnect_future = asyncio.get_running_loop().create_future()
    disconnect_future.set_exception(RuntimeError("lost"))

    with pytest.raises(RuntimeError, match="lost"):
        await cli_main._run_runner_with_disconnect_guard(
            runner=Runner(),
            vehicle=object(),
            disconnect_future=disconnect_future,
        )
