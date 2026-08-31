"""Unit tests for AERPAW forwarder ping and OEO severity coercion."""

from __future__ import annotations

from aerpawlib._internal.aerpaw_ping import ping_forward_server
from aerpawlib.v2.aerpaw import AerpawPlatform, OeoSeverity, coerce_oeo_severity


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_ping_slash_2xx_succeeds(monkeypatch):
    def fake_post(url, timeout=None):
        assert url.endswith("/ping/")
        return _Resp(200)

    monkeypatch.setattr("aerpawlib._internal.aerpaw_ping.requests.post", fake_post)
    assert ping_forward_server("127.0.0.1", 12435, 1.0) is True


def test_ping_http_400_is_not_connected(monkeypatch):
    monkeypatch.setattr(
        "aerpawlib._internal.aerpaw_ping.requests.post",
        lambda *a, **k: _Resp(400),
    )
    assert ping_forward_server("127.0.0.1", 12435, 1.0) is False


def test_ping_falls_back_to_unsashed_path(monkeypatch):
    def fake_post(url, timeout=None):
        if url.endswith("/ping/"):
            return _Resp(400)
        assert url.endswith("/ping")
        return _Resp(200)

    monkeypatch.setattr("aerpawlib._internal.aerpaw_ping.requests.post", fake_post)
    assert ping_forward_server("127.0.0.1", 12435, 1.0) is True


def test_v1_attach_uses_status_aware_ping(monkeypatch):
    from aerpawlib.v1.aerpaw import AERPAW

    monkeypatch.setattr(
        "aerpawlib.v1.aerpaw.ping_forward_server",
        lambda *a, **k: False,
    )
    platform = AERPAW.__new__(AERPAW)
    platform._forw_addr = "127.0.0.1"
    platform._forw_port = 12435
    assert platform.attach_to_aerpaw_platform() is False


def test_v2_check_connection_uses_status_aware_ping(monkeypatch):
    monkeypatch.setattr(
        "aerpawlib.v2.aerpaw.ping_forward_server",
        lambda *a, **k: True,
    )
    platform = AerpawPlatform.__new__(AerpawPlatform)
    platform.forward_ip = "127.0.0.1"
    platform.forward_port = 12435
    assert platform._check_connection() is True


def test_coerce_oeo_severity_accepts_strings():
    assert coerce_oeo_severity("CRITICAL") is OeoSeverity.CRITICAL
    assert coerce_oeo_severity("crit") is OeoSeverity.CRITICAL
    assert coerce_oeo_severity(OeoSeverity.WARNING) is OeoSeverity.WARNING
    assert coerce_oeo_severity("nope") is OeoSeverity.INFO


def test_build_oeo_url_accepts_string_severity(monkeypatch):
    monkeypatch.setattr("aerpawlib.v2.aerpaw.ping_forward_server", lambda *a, **k: False)
    platform = AerpawPlatform(suppress_stdout=True)
    url = platform._build_oeo_url("lost", "CRITICAL", None)
    assert "/oeo_msg/CRITICAL/" in url
