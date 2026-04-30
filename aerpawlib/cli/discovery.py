"""Discover user Runner class in experimenter scripts."""

import inspect
import logging

from aerpawlib.cli.constants import (
    API_CLASS_BASIC_RUNNER,
    API_CLASS_RUNNER,
    API_CLASS_STATE_MACHINE,
    API_CLASS_ZMQ_STATE_MACHINE,
)

logger = logging.getLogger("aerpawlib")


def is_direct_user_runner_class(candidate, runner_cls, framework_runner_classes):
    """True when candidate is a user runner directly inheriting a framework runner.

    We intentionally disallow user-defined runner inheritance chains (e.g.
    ``MyRunnerBase(StateMachine)`` then ``Mission(MyRunnerBase)``) to keep
    discovery unambiguous and consistent with the expected API usage.
    """
    if not inspect.isclass(candidate):
        return False
    if not issubclass(candidate, runner_cls):
        return False
    if candidate in framework_runner_classes:
        return False
    return any(base in framework_runner_classes for base in candidate.__bases__)


def discover_runner(api_module, experimenter_script):
    """Search for a Runner class in the experimenter script."""
    Runner = getattr(api_module, API_CLASS_RUNNER)
    StateMachine = getattr(api_module, API_CLASS_STATE_MACHINE)
    BasicRunner = getattr(api_module, API_CLASS_BASIC_RUNNER)
    ZmqStateMachine = getattr(api_module, API_CLASS_ZMQ_STATE_MACHINE, None)
    framework_runner_classes = [Runner, StateMachine, BasicRunner]
    if ZmqStateMachine:
        framework_runner_classes.append(ZmqStateMachine)

    runner = None
    flag_zmq_runner = False

    logger.debug("Searching for Runner class in script...")
    for name, val in inspect.getmembers(experimenter_script):
        if not is_direct_user_runner_class(val, Runner, framework_runner_classes):
            continue
        if ZmqStateMachine and issubclass(val, ZmqStateMachine):
            flag_zmq_runner = True
            logger.debug(f"Found ZmqStateMachine: {name}")
        if runner:
            logger.error("Multiple Runner classes found in script")
            raise Exception("You can only define one runner")
        logger.info(f"Found runner class: {name}")
        runner = val()

    if runner is None:
        logger.error("No Runner class found in script")
        raise Exception("No Runner class found in script")
    assert runner is not None

    return runner, flag_zmq_runner
