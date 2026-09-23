"""Checkpoint names must be URL-encoded so the server sees a single path segment."""

from urllib.parse import unquote, urlsplit

import pytest

from aerpawlib.v1.aerpaw import AERPAW
from aerpawlib.v2.aerpaw import AerpawPlatform

NAMES = ["plain", "has space", "a/b", "q?x=1", "frag#1", "amp&val"]


def _v1_platform():
    p = AERPAW.__new__(AERPAW)
    p._forw_addr = "127.0.0.1"
    p._forw_port = 12435
    return p


def _v2_platform():
    p = AerpawPlatform.__new__(AerpawPlatform)
    p.forward_ip = "127.0.0.1"
    p.forward_port = 12435
    return p


@pytest.mark.parametrize("make", [_v1_platform, _v2_platform], ids=["v1", "v2"])
@pytest.mark.parametrize("name", NAMES)
def test_checkpoint_name_is_one_path_segment(make, name):
    url = make()._checkpoint_build_request("string", name)
    parts = urlsplit(url)
    assert parts.query == ""
    assert parts.fragment == ""
    segments = parts.path.split("/")[1:]
    assert segments[:2] == ["checkpoint", "string"]
    assert len(segments) == 3
    assert unquote(segments[2]) == name
