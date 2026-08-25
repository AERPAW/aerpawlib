from types import SimpleNamespace

from typer.testing import CliRunner

from aerpawlib.__main__ import app
from aerpawlib.cli.constants import DEFAULT_SAFETY_CHECKER_PORT
from aerpawlib.cli.safety import (
    DEFAULT_CVM_SAFETY_CHECKER_IP,
    DEFAULT_LOCAL_SAFETY_CHECKER_IP,
    parse_underscore_safety_flags,
    resolve_safety_checker_target,
)


def test_resolve_skips_client_outside_aerpaw_without_flags():
    assert (
        resolve_safety_checker_target(
            ip=None,
            port=None,
            extra_args=["--file", "waypoints.csv"],
            is_aerpaw=False,
        )
        is None
    )


def test_resolve_uses_localhost_when_only_port_set_outside_aerpaw():
    assert resolve_safety_checker_target(ip=None, port=14580, is_aerpaw=False) == (
        DEFAULT_LOCAL_SAFETY_CHECKER_IP,
        14580,
    )


def test_resolve_uses_cvm_when_in_aerpaw_without_flags(monkeypatch):
    monkeypatch.delenv("AP_EXPENV_OEOCVM_XM", raising=False)
    assert resolve_safety_checker_target(ip=None, port=None, is_aerpaw=True) == (
        DEFAULT_CVM_SAFETY_CHECKER_IP,
        DEFAULT_SAFETY_CHECKER_PORT,
    )


def test_resolve_uses_oeo_env_for_aerpaw_default_ip(monkeypatch):
    monkeypatch.setenv("AP_EXPENV_OEOCVM_XM", "192.168.99.1")
    assert resolve_safety_checker_target(ip=None, port=None, is_aerpaw=True) == (
        "192.168.99.1",
        DEFAULT_SAFETY_CHECKER_PORT,
    )


def test_resolve_dashed_flags_win_over_underscore_extra_args():
    assert resolve_safety_checker_target(
        ip="10.0.0.5",
        port=14581,
        extra_args=["--safety_checker_ip", "192.168.32.25", "--safety_checker_port", "14580"],
        is_aerpaw=True,
    ) == ("10.0.0.5", 14581)


def test_resolve_copies_underscore_extra_args_when_typer_options_omitted():
    assert resolve_safety_checker_target(
        ip=None,
        port=None,
        extra_args=["--file", "out.csv", "--safety_checker_ip", "192.168.32.25", "--safety_checker_port", "14580"],
        is_aerpaw=True,
    ) == ("192.168.32.25", 14580)


def test_resolve_accepts_equals_form_underscore_flags():
    assert resolve_safety_checker_target(
        ip=None,
        port=None,
        extra_args=["--safety_checker_ip=10.1.2.3", "--safety_checker_port=14590"],
        is_aerpaw=False,
    ) == ("10.1.2.3", 14590)


def test_parse_underscore_flags_ignores_invalid_port():
    ip, port = parse_underscore_safety_flags(["--safety_checker_ip", "192.168.32.25", "--safety_checker_port", "nope"])
    assert ip == "192.168.32.25"
    assert port is None


def test_cli_passes_unmatched_args_to_the_script(monkeypatch, tmp_path):
    script = tmp_path / "mission.py"
    script.write_text(
        "from aerpawlib.v1.runner import BasicRunner\n"
        "class Mission(BasicRunner):\n"
        "    async def run(self, vehicle):\n"
        "        return None\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run(args: SimpleNamespace, unknown_args: list[str], experimenter_script: object) -> None:
        captured["ip"] = args.safety_checker_ip
        captured["port"] = args.safety_checker_port
        captured["unknown"] = list(unknown_args)

    monkeypatch.setattr("aerpawlib.__main__.run_v1_experiment", fake_run)
    result = CliRunner().invoke(
        app,
        [
            "--script",
            str(script),
            "--vehicle",
            "none",
            "--no-aerpaw-environment",
            "--safety_checker_ip",
            "192.168.32.25",
            "--safety_checker_port",
            "14580",
            "--file",
            "waypoints.csv",
        ],
    )
    assert result.exit_code == 0
    assert captured["ip"] is None
    assert captured["port"] is None
    unknown = captured["unknown"]
    assert isinstance(unknown, list)
    assert unknown == [
        "--safety_checker_ip",
        "192.168.32.25",
        "--safety_checker_port",
        "14580",
        "--file",
        "waypoints.csv",
    ]


def test_cli_consumes_dashed_safety_flags(monkeypatch, tmp_path):
    script = tmp_path / "mission.py"
    script.write_text(
        "from aerpawlib.v1.runner import BasicRunner\n"
        "class Mission(BasicRunner):\n"
        "    async def run(self, vehicle):\n"
        "        return None\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run(args: SimpleNamespace, unknown_args: list[str], experimenter_script: object) -> None:
        captured["ip"] = args.safety_checker_ip
        captured["port"] = args.safety_checker_port
        captured["unknown"] = list(unknown_args)

    monkeypatch.setattr("aerpawlib.__main__.run_v1_experiment", fake_run)
    result = CliRunner().invoke(
        app,
        [
            "--script",
            str(script),
            "--vehicle",
            "none",
            "--no-aerpaw-environment",
            "--safety-checker-ip",
            "10.0.0.5",
            "--safety-checker-port",
            "14581",
            "--file",
            "waypoints.csv",
        ],
    )
    assert result.exit_code == 0
    assert captured["ip"] == "10.0.0.5"
    assert captured["port"] == 14581
    assert captured["unknown"] == ["--file", "waypoints.csv"]
