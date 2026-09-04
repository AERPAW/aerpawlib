"""Probe the AERPAW OEO HTTP forwarder without treating HTTP 400 as success."""

from __future__ import annotations

import os

import requests

_AERPAW_ENV_MARKERS = (
    "AP_EXPENV_EXP_NUM",
    "AP_EXPENV_THIS_CONTAINER_EXP_NODE_NUM",
)


def aerpaw_env_vars_present() -> bool:
    """True when this process looks like an AERPAW experiment node."""
    return any(os.environ.get(name) for name in _AERPAW_ENV_MARKERS)


def ping_forward_server(host: str, port: int, timeout: float) -> bool:
    """Return True if the forwarder answers a ping with HTTP 2xx/3xx.

    Live consoles historically 400 ``/ping`` (single path segment) while
    ``/ping/`` reaches ``handle_ping``. Try the trailing-slash path first.
    """
    for path in ("/ping/", "/ping"):
        try:
            response = requests.post(
                f"http://{host}:{port}{path}",
                timeout=timeout,
            )
        except requests.exceptions.RequestException:
            continue
        if 200 <= response.status_code < 400:
            return True
    return False
