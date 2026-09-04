"""Discover user Runner class in experimenter scripts."""

from __future__ import annotations

import importlib
import inspect
import logging

from aerpawlib.cli.constants import (
    API_CLASS_BASIC_RUNNER,
    API_CLASS_RUNNER,
    API_CLASS_STATE_MACHINE,
    API_CLASS_ZMQ_STATE_MACHINE,
)

logger = logging.getLogger("aerpawlib")

_API_VERSIONS = ("v1", "v2")


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


def _framework_runner_classes(api_module):
    """Return the framework runner types exported by ``api_module``."""
    framework_runner = getattr(api_module, API_CLASS_RUNNER)
    state_machine = getattr(api_module, API_CLASS_STATE_MACHINE)
    basic_runner = getattr(api_module, API_CLASS_BASIC_RUNNER)
    zmq_state_machine = getattr(api_module, API_CLASS_ZMQ_STATE_MACHINE, None)
    classes = [framework_runner, state_machine, basic_runner]
    if zmq_state_machine:
        classes.append(zmq_state_machine)
    return framework_runner, classes


def script_has_runner(api_module, experimenter_script) -> bool:
    """True when the script defines exactly the kind of runner ``api_module`` expects."""
    framework_runner, framework_runner_classes = _framework_runner_classes(api_module)
    for _name, val in inspect.getmembers(experimenter_script):
        if is_direct_user_runner_class(val, framework_runner, framework_runner_classes):
            return True
    return False


def detect_script_api_versions(experimenter_script) -> list[str]:
    """Return the API versions (``v1`` / ``v2``) for which the script defines a runner."""
    found: list[str] = []
    for ver in _API_VERSIONS:
        api = importlib.import_module(f"aerpawlib.{ver}")
        if script_has_runner(api, experimenter_script):
            found.append(ver)
    return found


def resolve_api_version(requested: str | None, experimenter_script) -> str:
    """Choose v1/v2 from an explicit flag or the script's Runner class.

    Omitting ``--api-version`` infers the API from the script. Passing the
    wrong version (for example a v2 ``BasicRunner`` under default v1) raises
    ``ValueError`` instead of ``No Runner class found``.
    """
    detected = detect_script_api_versions(experimenter_script)
    if requested is None:
        if len(detected) == 1:
            return detected[0]
        if len(detected) > 1:
            raise ValueError("Script defines runners for both v1 and v2; pass --api-version v1 or v2")
        raise ValueError("No Runner class found in script")
    if requested not in _API_VERSIONS:
        raise ValueError(f"Invalid --api-version: {requested}")
    if detected and requested not in detected:
        raise ValueError(
            f"Script defines a {detected[0]} runner but --api-version is {requested}. Pass --api-version {detected[0]}.",
        )
    return requested


def discover_runner(api_module, experimenter_script):
    """Search for a Runner class in the experimenter script."""
    framework_runner, framework_runner_classes = _framework_runner_classes(api_module)
    zmq_state_machine = getattr(api_module, API_CLASS_ZMQ_STATE_MACHINE, None)

    found_runner = None
    flag_zmq_runner = False

    logger.debug("Searching for Runner class in script...")
    for name, val in inspect.getmembers(experimenter_script):
        if not is_direct_user_runner_class(
            val,
            framework_runner,
            framework_runner_classes,
        ):
            continue
        if zmq_state_machine and issubclass(val, zmq_state_machine):
            flag_zmq_runner = True
            logger.debug(f"Found ZmqStateMachine: {name}")
        if found_runner:
            logger.error("Multiple Runner classes found in script")
            raise Exception("You can only define one runner")
        logger.info(f"Found runner class: {name}")
        # Create the runner class because it would appear we found a valid one.
        # We will check for multiple valid classes above,
        # so we know this is the only one.
        found_runner = val()

    if found_runner is None:
        logger.error("No Runner class found in script")
        raise Exception("No Runner class found in script")
    assert found_runner is not None

    return found_runner, flag_zmq_runner
