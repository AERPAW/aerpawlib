"""Checkpoint transport failures: writes raise, reads return the "not set" value."""

import pytest
import requests

from aerpawlib.v1.aerpaw import AERPAW
from aerpawlib.v2.aerpaw import AerpawPlatform


def _v1_platform():
    p = AERPAW.__new__(AERPAW)
    p._forw_addr = "127.0.0.1"
    p._forw_port = 12435
    p._connected = True
    p._reping_forward_server = lambda: True
    return p


def _v2_platform():
    p = AerpawPlatform.__new__(AerpawPlatform)
    p.forward_ip = "127.0.0.1"
    p.forward_port = 12435
    p.is_connected = True
    p._reping_forward_server = lambda: True
    return p


@pytest.fixture
def refused(monkeypatch):
    """Every requests.get/post fails with a connection error; count the attempts."""
    attempts = []

    def fail(url, **_kwargs):
        attempts.append(url)
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", fail)
    monkeypatch.setattr(requests, "post", fail)
    monkeypatch.setattr("aerpawlib._internal.oeo_http.time.sleep", lambda _s: None)
    return attempts


WRITES = [
    ("checkpoint_reset_server", ()),
    ("checkpoint_set", ("ready",)),
    ("checkpoint_increment_counter", ("n",)),
    ("checkpoint_set_string", ("s", "v")),
]
READS = [
    ("checkpoint_check", ("ready",), False),
    ("checkpoint_check_counter", ("n",), 0),
    ("checkpoint_check_string", ("s",), ""),
]


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
@pytest.mark.parametrize(("method", "args"), WRITES)
def test_write_raises_after_retry(make, method, args, refused):
    with pytest.raises(requests.exceptions.ConnectionError):
        getattr(make(), method)(*args)
    assert len(refused) == 2


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
@pytest.mark.parametrize(("method", "args", "not_set"), READS)
def test_read_returns_not_set_after_retry(make, method, args, not_set, refused):
    assert getattr(make(), method)(*args) == not_set
    assert len(refused) == 2
