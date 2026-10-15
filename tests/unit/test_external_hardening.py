"""Regression tests for ExternalProcess: no shell (v1), no pipe deadlock,
kill unblocks waits, UTF-8 decoding, and structured-log robustness."""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import warnings

import pytest

from aerpawlib._internal import subprocess_io
from aerpawlib.structured_log import StructuredEventLogger
from aerpawlib.v1.external import ExternalProcess as V1ExternalProcess
from aerpawlib.v2.external import ExternalProcess as V2ExternalProcess

BOUND_S = 5.0
BIG_OUTPUT = "import sys\nfor i in range(6000):\n    sys.stdout.write('line %05d ' % i + 'x' * 40 + '\\n')\nsys.stdout.flush()\n"
BIG_THEN_SLEEP = BIG_OUTPUT + "import time\ntime.sleep(30)\n"
IGNORE_TERM_AND_FLOOD = "import signal, sys, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n" + BIG_THEN_SLEEP

BOTH = pytest.mark.parametrize("cls", [V1ExternalProcess, V2ExternalProcess], ids=["v1", "v2"])


# --- #4 v1 runs without a shell ----------------------------------------------------


@pytest.mark.asyncio
async def test_v1_params_are_not_shell_interpreted(tmp_path):
    marker = tmp_path / "pwned"
    ep = V1ExternalProcess("echo", params=[f"safe; touch {marker}"])
    await ep.start()
    try:
        line = await asyncio.wait_for(ep.read_line(), BOUND_S)
        await asyncio.wait_for(ep.wait_until_terminated(), BOUND_S)
    finally:
        await ep.aclose()
    assert line == f"safe; touch {marker}"
    assert not marker.exists()


@pytest.mark.asyncio
async def test_v1_redirect_paths_are_real_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "pwned"
    src = tmp_path / "in.txt"
    src.write_text("hello from file\n")
    dst = tmp_path / "out.txt; touch pwned"
    ep = V1ExternalProcess("cat", stdin=str(src), stdout=str(dst))
    await ep.start()
    try:
        await asyncio.wait_for(ep.wait_until_terminated(), BOUND_S)
        assert await ep.read_line() is None
    finally:
        await ep.aclose()
    assert dst.read_text() == "hello from file\n"
    assert not marker.exists()


@pytest.mark.asyncio
async def test_v1_executable_with_spaces_still_runs_without_shell(tmp_path):
    marker = tmp_path / "pwned"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ep = V1ExternalProcess(f"echo hi;touch {marker}")
        await ep.start()
    try:
        line = await asyncio.wait_for(ep.read_line(), BOUND_S)
    finally:
        await ep.aclose()
    assert line == f"hi;touch {marker}"
    assert not marker.exists()
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


# --- #5 full pipe deadlock / kill ----------------------------------------------------


@BOTH
@pytest.mark.asyncio
async def test_wait_until_terminated_does_not_deadlock_on_full_pipe(cls):
    ep = cls(sys.executable, params=["-c", BIG_OUTPUT])
    await ep.start()
    try:
        await asyncio.wait_for(ep.wait_until_terminated(), BOUND_S)
        assert ep.process.returncode == 0
        first = await asyncio.wait_for(ep.read_line(), BOUND_S)
        assert first is not None and first.startswith("line 00000")
    finally:
        await ep.aclose()


@BOTH
@pytest.mark.asyncio
async def test_kill_unblocks_wait_until_terminated(cls):
    ep = cls(sys.executable, params=["-c", BIG_THEN_SLEEP])
    await ep.start()
    try:
        waiter = asyncio.ensure_future(ep.wait_until_terminated())
        await asyncio.sleep(0.3)
        ep.process.kill()
        await asyncio.wait_for(waiter, BOUND_S)
        assert ep.process.returncode is not None
    finally:
        await ep.aclose()


@BOTH
@pytest.mark.asyncio
async def test_aclose_is_bounded_when_child_ignores_sigterm(cls, monkeypatch):
    monkeypatch.setattr(subprocess_io, "TERMINATE_TIMEOUT_S", 0.3)
    ep = cls(sys.executable, params=["-c", IGNORE_TERM_AND_FLOOD])
    await ep.start()
    await asyncio.sleep(0.3)
    t0 = time.monotonic()
    await asyncio.wait_for(ep.aclose(), BOUND_S)
    assert time.monotonic() - t0 < BOUND_S
    assert ep.process.returncode is not None


# --- #6 UTF-8 decoding ------------------------------------------------------------------


@BOTH
@pytest.mark.asyncio
async def test_read_line_decodes_utf8_and_replaces_invalid(cls):
    script = "import sys\nsys.stdout.buffer.write('caf\\u00e9\\n'.encode('utf-8') + b'bad\\xff\\n')\n"
    ep = cls(sys.executable, params=["-c", script])
    await ep.start()
    try:
        first = await asyncio.wait_for(ep.read_line(), BOUND_S)
        second = await asyncio.wait_for(ep.read_line(), BOUND_S)
    finally:
        await ep.aclose()
    assert first == "caf\u00e9"
    assert second == "bad\ufffd"


# --- #16 structured log never raises on non-JSON values ------------------------------------


def test_structured_log_serializes_unknown_values_with_str():
    class Coordinate:
        def __str__(self) -> str:
            return "Coordinate(1, 2, 3)"

    out = io.StringIO()
    log = StructuredEventLogger(out)
    log.log_event("goto", target=Coordinate(), nested={"c": Coordinate()})
    record = json.loads(out.getvalue())
    assert record["target"] == "Coordinate(1, 2, 3)"
    assert record["nested"] == {"c": "Coordinate(1, 2, 3)"}


def test_structured_log_drops_unserializable_event():
    out = io.StringIO()
    log = StructuredEventLogger(out)
    cyclic: dict = {}
    cyclic["self"] = cyclic
    log.log_event("bad", data=cyclic)
    log.log_event("good")
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "good"
