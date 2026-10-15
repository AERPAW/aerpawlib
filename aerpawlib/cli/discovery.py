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

    Kept for backward compatibility. Discovery itself accepts user inheritance
    chains and picks the most-derived class (see ``discover_runner``).
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


class RunnerDiscoveryError(Exception):
    """Raised when a script defines no runner, or more than one candidate runner."""


def _is_user_runner_class(candidate, runner_cls, framework_runner_classes) -> bool:
    """True for any non-framework subclass of ``runner_cls`` (direct or indirect)."""
    if not inspect.isclass(candidate):
        return False
    if not issubclass(candidate, runner_cls):
        return False
    return candidate not in framework_runner_classes


def _user_runner_classes(api_module, experimenter_script) -> list[tuple[str, type]]:
    """Return ``(name, cls)`` for each distinct user runner class in the script.

    Aliases (``Alias = Mission``) are collapsed by class identity. Classes
    defined in the script module win; imported runners (e.g. a base class from
    a helper module) are only considered when the script defines none itself.
    Nothing is instantiated here.
    """
    framework_runner, framework_runner_classes = _framework_runner_classes(api_module)
    found: list[tuple[str, type]] = []
    seen: set[int] = set()
    for name, val in inspect.getmembers(experimenter_script):
        if not _is_user_runner_class(val, framework_runner, framework_runner_classes):
            continue
        if id(val) in seen:
            continue
        seen.add(id(val))
        found.append((name, val))
    module_name = getattr(experimenter_script, "__name__", None)
    local = [(n, c) for n, c in found if c.__module__ == module_name]
    if local:
        return local
    return [(n, c) for n, c in found if not (c.__module__ or "").startswith("aerpawlib.")]


def _select_runner_class(candidates: list[tuple[str, type]]) -> tuple[str, type]:
    """Pick the single most-derived runner; reject unrelated (ambiguous) runners.

    A user base class and its subclass resolve to the subclass. Two runners
    that are not on one inheritance chain are ambiguous and rejected.
    """
    leaves = [(n, c) for n, c in candidates if not any(o is not c and issubclass(o, c) for _, o in candidates)]
    if len(leaves) != 1:
        names = ", ".join(sorted(n for n, _ in leaves))
        logger.error("Multiple Runner classes found in script: %s", names)
        raise RunnerDiscoveryError(
            f"You can only define one runner (found unrelated runner classes: {names})",
        )
    return leaves[0]


def script_has_runner(api_module, experimenter_script) -> bool:
    """True when the script defines exactly the kind of runner ``api_module`` expects."""
    return bool(_user_runner_classes(api_module, experimenter_script))


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
    """Search for a Runner class in the experimenter script.

    Only classes defined in the script are considered (imported runners are a
    fallback when the script defines none). The most-derived class of a user
    inheritance chain is chosen. Ambiguous sets are rejected before any runner
    is instantiated.
    """
    zmq_state_machine = getattr(api_module, API_CLASS_ZMQ_STATE_MACHINE, None)

    logger.debug("Searching for Runner class in script...")
    candidates = _user_runner_classes(api_module, experimenter_script)
    if not candidates:
        logger.error("No Runner class found in script")
        raise RunnerDiscoveryError("No Runner class found in script")
    name, runner_cls = _select_runner_class(candidates)
    if len(candidates) > 1:
        logger.info(
            "Using most-derived runner class %s (also defined: %s)",
            name,
            ", ".join(sorted(n for n, c in candidates if c is not runner_cls)),
        )
    flag_zmq_runner = bool(zmq_state_machine and issubclass(runner_cls, zmq_state_machine))
    if flag_zmq_runner:
        logger.debug(f"Found ZmqStateMachine: {name}")
    logger.info(f"Found runner class: {name}")
    return runner_cls(), flag_zmq_runner


def initialize_script_args(runner, extra_args) -> None:
    """Run the script's ``initialize_args`` and turn its ``SystemExit`` into a failed run.

    Call this before connecting anything. Scripts typically call
    ``ArgumentParser.parse_args(extra_args)``; a bad flag exits 2 and
    ``-- --help`` exits 0. Neither is a successful mission, so the CLI exits
    nonzero in both cases.
    """
    try:
        runner.initialize_args(extra_args)
    except SystemExit as e:
        code = e.code
        if isinstance(code, int) and code != 0:
            logger.error("Script argument parsing failed (exit code %d); not starting the experiment.", code)
            raise SystemExit(code) from None
        logger.error("Script argument parsing exited (%r, e.g. --help); not starting the experiment.", code)
        raise SystemExit(1) from None
