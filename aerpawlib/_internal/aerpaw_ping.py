"""Probe the AERPAW OEO HTTP forwarder without treating HTTP 400 as success."""

from __future__ import annotations

import requests


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
