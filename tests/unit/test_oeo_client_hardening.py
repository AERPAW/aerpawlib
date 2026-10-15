"""Regression tests for OEO client fixes: checkpoint transport errors are
retried/logged instead of raised, non-2xx publishes fail, async timeouts
do not escape."""

from __future__ import annotations

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
import requests

import aerpawlib.v1.aerpaw as v1_aerpaw
import aerpawlib.v2.aerpaw as v2_aerpaw

BOUND_S = 5.0


def _v2_platform(monkeypatch, host="127.0.0.1", port=1) -> v2_aerpaw.AerpawPlatform:
    monkeypatch.setattr(v2_aerpaw, "ping_forward_server", lambda *a, **k: True)
    return v2_aerpaw.AerpawPlatform(host, port, suppress_stdout=True)


def _v1_platform(monkeypatch, host="127.0.0.1", port=1) -> v1_aerpaw.AERPAW:
    monkeypatch.setattr(v1_aerpaw, "ping_forward_server", lambda *a, **k: True)
    return v1_aerpaw.AERPAW(host, port)


def _failing_requests(monkeypatch, calls: list[str]):
    def fail(url, **kwargs):
        calls.append(url)
        raise requests.exceptions.ReadTimeout("read timeout")

    monkeypatch.setattr(requests, "post", fail)
    monkeypatch.setattr(requests, "get", fail)


CHECKPOINT_CASES = [
    ("checkpoint_reset_server", (), False),
    ("checkpoint_set", ("cp",), False),
    ("checkpoint_increment_counter", ("ctr",), False),
    ("checkpoint_set_string", ("key", "value"), False),
    ("checkpoint_check", ("cp",), False),
    ("checkpoint_check_counter", ("ctr",), 0),
    ("checkpoint_check_string", ("key",), ""),
]


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
@pytest.mark.parametrize(("method", "args", "expected"), CHECKPOINT_CASES)
def test_checkpoint_transport_error_does_not_raise(monkeypatch, make, method, args, expected):
    platform = make(monkeypatch)
    calls: list[str] = []
    _failing_requests(monkeypatch, calls)
    t0 = time.monotonic()
    result = getattr(platform, method)(*args)
    assert result == expected
    # Re-ping succeeded (patched True), so it retried once.
    assert len(calls) == 2
    assert time.monotonic() - t0 < BOUND_S


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
def test_checkpoint_does_not_retry_when_reping_fails(monkeypatch, make):
    platform = make(monkeypatch)
    calls: list[str] = []
    _failing_requests(monkeypatch, calls)
    mod = v1_aerpaw if make is _v1_platform else v2_aerpaw
    monkeypatch.setattr(mod, "ping_forward_server", lambda *a, **k: False)
    assert platform.checkpoint_set("cp") is False
    assert len(calls) == 1


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
def test_checkpoint_set_success_returns_true(monkeypatch, make):
    platform = make(monkeypatch)
    monkeypatch.setattr(requests, "post", lambda url, **k: SimpleNamespace(status_code=200, content=b""))
    assert platform.checkpoint_set("cp") is True


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
def test_checkpoint_http_error_still_raises(monkeypatch, make):
    platform = make(monkeypatch)
    monkeypatch.setattr(requests, "post", lambda url, **k: SimpleNamespace(status_code=500, content=b""))
    with pytest.raises(Exception, match="error when posting"):
        platform.checkpoint_set("cp")


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
@pytest.mark.parametrize("status", [400, 500, 503])
def test_publish_user_topic_non_2xx_is_failure(monkeypatch, make, status):
    platform = make(monkeypatch)
    monkeypatch.setattr(requests, "post", lambda url, **k: SimpleNamespace(status_code=status))
    assert platform.publish_user_oeo_topic("1", "radio/snr") is False


# --- async variants against a real local HTTP server ------------------------------------


class _Handler(BaseHTTPRequestHandler):
    mode = "500"

    def do_POST(self):
        if self.mode == "hang":
            time.sleep(1.5)
        self.send_response(500 if self.mode == "500" else 200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def local_http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.asyncio
async def test_publish_async_non_2xx_is_failure(monkeypatch, local_http_server):
    _Handler.mode = "500"
    platform = _v2_platform(monkeypatch, port=local_http_server.server_address[1])
    ok = await asyncio.wait_for(platform.publish_user_oeo_topic_async("1", "radio/snr"), BOUND_S)
    assert ok is False


@pytest.mark.asyncio
async def test_async_oeo_timeouts_do_not_escape(monkeypatch, local_http_server):
    _Handler.mode = "hang"
    monkeypatch.setattr(v2_aerpaw, "AERPAW_OEO_MSG_TIMEOUT_S", 0.2)
    platform = _v2_platform(monkeypatch, port=local_http_server.server_address[1])
    await asyncio.wait_for(platform.log_to_oeo_async("hello"), BOUND_S)
    ok = await asyncio.wait_for(platform.publish_user_oeo_topic_async("1", "radio/snr"), BOUND_S)
    assert ok is False
