"""Regression tests for CLI fail-closed fixes (runner discovery, script loading,
argument validation, connect cleanup, signals, and v1/v2 experiment exits)."""

from __future__ import annotations

import asyncio
import logging
import signal
import subprocess
import sys
import textwrap
import time
import types
import uuid
from pathlib import Path
from typing import Any, ClassVar

import pytest
from typer.testing import CliRunner

from aerpawlib import __main__ as cli_main
from aerpawlib.cli import process_guard
from aerpawlib.cli.config_merge import config_dict_to_cli_args
from aerpawlib.cli.disconnect import (
    VehicleClosedDuringMissionError,
    run_runner_with_disconnect_guard,
    validate_heartbeat_timeout,
    wait_for_v1_connection_loss,
)
from aerpawlib.cli.discovery import RunnerDiscoveryError, discover_runner
from aerpawlib.cli.experiments_v1 import run_blocking_until_shutdown, run_v1_experiment
from aerpawlib.cli.experiments_v2 import run_v2_experiment
from aerpawlib.v1.exceptions import HeartbeatLostError

BOUND_S = 5.0


@pytest.fixture(autouse=True)
def _cli_logger_and_signals(monkeypatch):
    cli_main.logger = logging.getLogger("aerpawlib.test")
    # The experiment runners install process-wide mavsdk_server tracking; keep
    # it (and its "reject new servers" latch) from leaking into other tests.
    from mavsdk import system as mavsdk_system

    monkeypatch.setattr(mavsdk_system.System, "_start_mavsdk_server", mavsdk_system.System.__dict__["_start_mavsdk_server"])
    monkeypatch.setattr(process_guard, "_installed", False)
    monkeypatch.setattr(process_guard, "_spawned", [])
    monkeypatch.setattr(process_guard, "_reject_new", False)
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def _fake_api():
    class Runner:
        def __init__(self) -> None:
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


def _script_module(name: str, **classes: type) -> types.ModuleType:
    script = types.ModuleType(name)
    for attr, cls in classes.items():
        if cls.__module__ != name and attr == cls.__name__:
            cls.__module__ = name
        setattr(script, attr, cls)
    return script


# --- #1 / #14 runner discovery -------------------------------------------------


def test_discovery_picks_most_derived_user_runner():
    api = _fake_api()

    class BaseMission(api.BasicRunner):
        pass

    class Child(BaseMission):
        pass

    script = _script_module("mission_chain", BaseMission=BaseMission, Child=Child)
    runner, is_zmq = discover_runner(api, script)
    assert type(runner) is Child
    assert is_zmq is False


def test_discovery_ignores_imported_runner_when_script_defines_one():
    api = _fake_api()

    class Imported(api.StateMachine):
        pass

    Imported.__module__ = "some_helper_module"

    class Mission(api.StateMachine):
        pass

    script = _script_module("mission_local", Mission=Mission)
    script.Imported = Imported
    runner, _ = discover_runner(api, script)
    assert type(runner) is Mission


def test_discovery_rejects_unrelated_runners_before_instantiating():
    api = _fake_api()
    constructed: list[str] = []

    class Alpha(api.BasicRunner):
        def __init__(self) -> None:
            constructed.append("Alpha")

    class Zulu(api.StateMachine):
        def __init__(self) -> None:
            constructed.append("Zulu")

    script = _script_module("mission_two", Alpha=Alpha, Zulu=Zulu)
    with pytest.raises(RunnerDiscoveryError, match="only define one runner"):
        discover_runner(api, script)
    assert constructed == []


def test_discovery_dedupes_aliases():
    api = _fake_api()
    constructed: list[str] = []

    class Mission(api.BasicRunner):
        def __init__(self) -> None:
            constructed.append("Mission")

    script = _script_module("mission_alias", Mission=Mission)
    script.MissionAlias = Mission
    runner, _ = discover_runner(api, script)
    assert type(runner) is Mission
    assert constructed == ["Mission"]


# --- #12 / #13 script loading ----------------------------------------------------


@pytest.fixture
def isolated_import_state():
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    yield
    sys.path[:] = saved_path
    for name in set(sys.modules) - saved_modules:
        del sys.modules[name]


def test_loader_supports_package_relative_imports(tmp_path, isolated_import_state):
    pkg = f"relimp_{uuid.uuid4().hex[:8]}"
    pkg_dir = tmp_path / pkg
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "helper.py").write_text("VALUE = 41\n")
    (pkg_dir / "mission.py").write_text("from .helper import VALUE\nANSWER = VALUE + 1\n")
    module = cli_main._load_script_from_path(str(pkg_dir / "mission.py"))
    assert module.ANSWER == 42
    assert module.__name__ == f"{pkg}.mission"
    assert sys.modules[f"{pkg}.mission"] is module


def test_loader_registers_module_for_circular_imports(tmp_path, isolated_import_state):
    name = f"mission_{uuid.uuid4().hex[:8]}"
    (tmp_path / f"{name}_helper.py").write_text(
        textwrap.dedent(
            f"""
            import {name}
            SEEN = {name}
            """,
        ),
    )
    (tmp_path / f"{name}.py").write_text(f"MARK = object()\nimport {name}_helper\n")
    module = cli_main._load_script_from_path(str(tmp_path / f"{name}.py"))
    assert sys.modules[name] is module
    assert sys.modules[f"{name}_helper"].SEEN is module


def test_loader_loads_existing_extensionless_path(tmp_path, isolated_import_state):
    name = f"ext_{uuid.uuid4().hex[:8]}"
    (tmp_path / name).write_text("WHICH = 'extensionless'\n")
    (tmp_path / f"{name}.py").write_text("WHICH = 'decoy'\n")
    module = cli_main._load_script_from_path(str(tmp_path / name))
    assert module.WHICH == "extensionless"


def test_loader_appends_py_only_when_path_missing(tmp_path, isolated_import_state):
    name = f"noext_{uuid.uuid4().hex[:8]}"
    (tmp_path / f"{name}.py").write_text("WHICH = 'py'\n")
    module = cli_main._load_script_from_path(str(tmp_path / name))
    assert module.WHICH == "py"


# --- #2 blank --conn / #8 heartbeat timeout validation ----------------------------


@pytest.mark.parametrize("conn", ["", " ", "\t "])
def test_cli_rejects_blank_conn(conn):
    result = CliRunner().invoke(
        cli_main.app,
        ["--script", "does_not_matter.py", "--vehicle", "drone", "--conn", conn],
    )
    assert result.exit_code == 1
    assert "--connection must be provided" in result.output


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1"])
def test_cli_rejects_bad_heartbeat_timeout(value):
    result = CliRunner().invoke(
        cli_main.app,
        ["--script", "x.py", "--vehicle", "none", f"--heartbeat-timeout={value}"],
    )
    assert result.exit_code == 1
    assert "--heartbeat-timeout must be a finite number > 0" in result.output


@pytest.mark.parametrize("value", [0, -1.0, float("nan"), float("inf")])
def test_validate_heartbeat_timeout_rejects(value):
    with pytest.raises(ValueError):
        validate_heartbeat_timeout(value)


@pytest.mark.asyncio
async def test_v1_connection_watcher_rejects_zero_timeout():
    vehicle = types.SimpleNamespace(closed=False, connected=True, _connection_error=None)
    with pytest.raises(ValueError):
        await asyncio.wait_for(wait_for_v1_connection_loss(vehicle, 0, HeartbeatLostError), BOUND_S)


# --- #10 config booleans -----------------------------------------------------------


@pytest.mark.parametrize("value", ["false", "False", "0", "no", False])
def test_config_false_strings_do_not_enable_flag(value):
    assert config_dict_to_cli_args({"skip-rtl": value}) == []


@pytest.mark.parametrize("value", [True, "true", "yes", "1"])
def test_config_true_values_enable_flag(value):
    assert config_dict_to_cli_args({"skip-rtl": value}) == ["--skip-rtl"]


@pytest.mark.parametrize("value", [0, 1, 0.0, "maybe", ["x"], {"a": 1}])
def test_config_rejects_non_boolean_for_flag(value):
    with pytest.raises(ValueError, match="boolean flag"):
        config_dict_to_cli_args({"skip-init": value})


def test_config_non_flag_keys_unchanged():
    assert config_dict_to_cli_args({"conn": "udpin://:14550", "my-flag": True}) == [
        "--conn",
        "udpin://:14550",
        "--my-flag",
    ]


# --- #7 disconnect watcher finishing because the vehicle closed ----------------------


@pytest.mark.asyncio
async def test_vehicle_closed_mid_mission_is_failure():
    vehicle = types.SimpleNamespace(_closed=False, connected=True, _connection_error=None)
    runner_cancelled: list[bool] = []

    class Runner:
        async def run(self, _vehicle):
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                runner_cancelled.append(True)
                raise

    async def close_soon():
        await asyncio.sleep(0.05)
        vehicle._closed = True

    watcher = asyncio.ensure_future(wait_for_v1_connection_loss(vehicle, 5.0, HeartbeatLostError))
    closer = asyncio.ensure_future(close_soon())
    with pytest.raises(VehicleClosedDuringMissionError):
        await asyncio.wait_for(
            run_runner_with_disconnect_guard(runner=Runner(), vehicle=vehicle, disconnect_future=watcher),
            BOUND_S,
        )
    await closer
    assert runner_cancelled == [True]


# --- #9 second signal / v1 preflight off the loop -------------------------------------


def test_second_sigint_forces_exit(tmp_path):
    script = tmp_path / "swallow.py"
    script.write_text(
        textwrap.dedent(
            """
            import signal, sys, time
            from aerpawlib.cli.process_guard import ShutdownSignalHandler
            first = []
            handler = ShutdownSignalHandler(lambda: first.append(1))
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
            print("READY", flush=True)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                time.sleep(0.01)   # a mission that ignores the graceful request
            sys.exit(0)
            """,
        ),
    )
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        cwd=str(repo_root),
        env={"PYTHONPATH": str(repo_root), "PATH": "/usr/bin:/bin"},
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == b"READY"
        proc.send_signal(signal.SIGINT)
        time.sleep(0.2)
        assert proc.poll() is None, "first SIGINT must only request graceful shutdown"
        proc.send_signal(signal.SIGINT)
        rc = proc.wait(timeout=BOUND_S)
        assert rc == -signal.SIGINT
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.asyncio
async def test_v1_preflight_returns_on_shutdown():
    shutdown = asyncio.Event()

    def blocking_preflight(_should_arm: bool) -> None:
        time.sleep(3)

    async def request_shutdown():
        await asyncio.sleep(0.05)
        shutdown.set()

    t0 = time.monotonic()
    trigger = asyncio.ensure_future(request_shutdown())
    finished = await asyncio.wait_for(run_blocking_until_shutdown(blocking_preflight, shutdown, True), BOUND_S)
    await trigger
    assert finished is False
    assert time.monotonic() - t0 < 1.0


@pytest.mark.asyncio
async def test_v1_preflight_exception_propagates():
    def failing_preflight(_should_arm: bool) -> None:
        raise RuntimeError("preflight exploded")

    with pytest.raises(RuntimeError, match="preflight exploded"):
        await asyncio.wait_for(run_blocking_until_shutdown(failing_preflight, asyncio.Event(), True), BOUND_S)


# --- #2 mavsdk_server cleanup ----------------------------------------------------------


@pytest.fixture
def fake_mavsdk_server(monkeypatch):
    """Route mavsdk.System._start_mavsdk_server to a harmless sleeping child."""
    from mavsdk import system as mavsdk_system

    started: list[subprocess.Popen] = []

    def fake_start(system_address, port, sysid, compid):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        started.append(proc)
        return proc

    monkeypatch.setattr(mavsdk_system.System, "_start_mavsdk_server", staticmethod(fake_start))
    yield started
    for proc in started:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _cli_args(**overrides: Any) -> types.SimpleNamespace:
    args = types.SimpleNamespace(
        config=None,
        script="x.py",
        conn="",
        vehicle="none",
        api_version=None,
        initialize=False,
        rtl_at_end=True,
        no_stdout=True,
        no_status_bar=True,
        no_aerpaw_environment=True,
        run_zmq_proxy=False,
        zmq_identifier=None,
        zmq_proxy_server=None,
        verbose=False,
        quiet=True,
        log_file=None,
        structured_log=None,
        conn_timeout=2.0,
        heartbeat_timeout=5.0,
        mavsdk_port=50051,
        safety_checker_port=None,
        safety_checker_ip=None,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _v2_script(name: str, ran: list[str], *, raise_in_args: BaseException | None = None):
    from aerpawlib.v2.runner import BasicRunner, entrypoint

    class Mission(BasicRunner):
        def initialize_args(self, extra_args):
            if raise_in_args is not None:
                raise raise_in_args

        @entrypoint
        async def go(self, vehicle):
            ran.append("ran")

    Mission.__module__ = name
    module = types.ModuleType(name)
    module.Mission = Mission
    return module


def test_v2_connect_failure_kills_mavsdk_server(monkeypatch, fake_mavsdk_server):
    from mavsdk.system import System

    import aerpawlib.v2 as v2

    async def failing_connect(cls, *args, **kwargs):
        System._start_mavsdk_server("udpin://127.0.0.1:1", 59999, 245, 190)
        raise TimeoutError("no heartbeat")

    monkeypatch.setattr(v2.DummyVehicle, "connect", classmethod(failing_connect))
    ran: list[str] = []
    with pytest.raises(SystemExit) as exc:
        run_v2_experiment(_cli_args(), [], _v2_script("v2_connect_fail", ran))
    assert exc.value.code == 1
    assert ran == []
    assert fake_mavsdk_server, "fake server should have been started"
    assert all(proc.poll() is not None for proc in fake_mavsdk_server)


def test_server_started_after_failure_is_killed(fake_mavsdk_server):
    from mavsdk.system import System

    process_guard.install_mavsdk_server_tracking()
    process_guard.kill_mavsdk_servers(reject_new=True)
    proc = System._start_mavsdk_server(None, 59998, 245, 190)
    assert proc.poll() is not None


# --- #4 preflight exception / #5 script args SystemExit (v2) ----------------------------


def test_v2_preflight_exception_fails_run(monkeypatch):
    import aerpawlib.v2 as v2

    async def boom(self, *args, **kwargs):
        raise RuntimeError("preflight exploded")

    monkeypatch.setattr(v2.DummyVehicle, "initialize", boom, raising=False)
    ran: list[str] = []
    with pytest.raises(SystemExit) as exc:
        run_v2_experiment(_cli_args(initialize=True), [], _v2_script("v2_preflight_fail", ran))
    assert exc.value.code == 1
    assert ran == []


@pytest.mark.parametrize(("raised", "expected"), [(SystemExit(0), 1), (SystemExit(2), 2), (SystemExit(None), 1)])
def test_v2_script_args_exit_happens_before_connect(monkeypatch, raised, expected):
    import aerpawlib.v2 as v2

    connects: list[bool] = []

    async def recording_connect(cls, *args, **kwargs):
        connects.append(True)
        raise AssertionError("must not connect")

    monkeypatch.setattr(v2.DummyVehicle, "connect", classmethod(recording_connect))
    ran: list[str] = []
    with pytest.raises(SystemExit) as exc:
        run_v2_experiment(_cli_args(), [], _v2_script("v2_args_exit", ran, raise_in_args=raised))
    assert exc.value.code == expected
    assert connects == []


# --- #5 / #6 / #11 v1 experiment exits -------------------------------------------------


class _RecordingV1Vehicle:
    instances: ClassVar[list[_RecordingV1Vehicle]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.closed_calls = 0
        self._closed = False
        _RecordingV1Vehicle.instances.append(self)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self.closed_calls += 1
        self._closed = True


def _v1_script(name: str, ran: list[str], *, raise_in_args: BaseException | None = None):
    from aerpawlib.v1.runner import BasicRunner, entrypoint

    class Mission(BasicRunner):
        def initialize_args(self, extra_args):
            if raise_in_args is not None:
                raise raise_in_args

        @entrypoint
        async def go(self, vehicle):
            ran.append("ran")

    Mission.__module__ = name
    module = types.ModuleType(name)
    module.Mission = Mission
    return module


class _PlatformSpy:
    def __init__(self, connected: bool) -> None:
        self.__dict__["reads"] = []
        self.__dict__["connected"] = connected

    @property
    def _connected(self) -> bool:
        self.reads.append("_connected")
        return self.connected

    def log_to_oeo(self, *args: Any, **kwargs: Any) -> None:
        pass


def test_v1_not_in_aerpaw_exit_closes_vehicle(monkeypatch):
    import aerpawlib.v1 as v1

    _RecordingV1Vehicle.instances = []
    monkeypatch.setattr(v1, "DummyVehicle", _RecordingV1Vehicle)
    monkeypatch.setattr(v1, "AERPAW_Platform", _PlatformSpy(connected=False))
    ran: list[str] = []
    with pytest.raises(SystemExit) as exc:
        run_v1_experiment(_cli_args(no_aerpaw_environment=False), [], _v1_script("v1_not_aerpaw", ran))
    assert exc.value.code == 1
    assert ran == []
    assert len(_RecordingV1Vehicle.instances) == 1
    assert _RecordingV1Vehicle.instances[0].closed_calls >= 1


def test_v1_no_aerpaw_environment_does_not_touch_platform(monkeypatch):
    import aerpawlib.v1 as v1

    spy = _PlatformSpy(connected=True)
    _RecordingV1Vehicle.instances = []
    monkeypatch.setattr(v1, "DummyVehicle", _RecordingV1Vehicle)
    monkeypatch.setattr(v1, "AERPAW_Platform", spy)
    ran: list[str] = []
    with pytest.raises(SystemExit) as exc:
        run_v1_experiment(_cli_args(no_aerpaw_environment=True, no_stdout=False), [], _v1_script("v1_standalone", ran))
    assert exc.value.code == 0
    assert ran == ["ran"]
    assert spy.reads == []


def test_v1_script_args_exit_happens_before_connect(monkeypatch):
    import aerpawlib.v1 as v1

    _RecordingV1Vehicle.instances = []
    monkeypatch.setattr(v1, "DummyVehicle", _RecordingV1Vehicle)
    ran: list[str] = []
    with pytest.raises(SystemExit) as exc:
        run_v1_experiment(_cli_args(), [], _v1_script("v1_args_exit", ran, raise_in_args=SystemExit(0)))
    assert exc.value.code == 1
    assert _RecordingV1Vehicle.instances == []
