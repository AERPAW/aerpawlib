import logging
import types

import pytest

from aerpawlib import __main__ as cli_main


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

