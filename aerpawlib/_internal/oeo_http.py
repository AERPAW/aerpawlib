"""Bounded-retry HTTP to the AERPAW OEO forwarder (checkpoints).

Transport failures are retried once the forwarder answers a fresh ping. Reads
then report the failure by returning ``None`` (the caller returns its "not
set" value). Writes pass ``raise_on_failure`` so a lost checkpoint update is
raised instead of silently leaving peers waiting.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

logger = logging.getLogger("aerpawlib")

CHECKPOINT_ATTEMPTS = 2
"""Total attempts for one checkpoint request on transport errors."""

CHECKPOINT_RETRY_DELAY_S = 0.25
"""Pause between checkpoint attempts (after a successful re-ping)."""


def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float,
    reping: Callable[[], bool] | None = None,
    attempts: int = CHECKPOINT_ATTEMPTS,
    retry_delay_s: float = CHECKPOINT_RETRY_DELAY_S,
    log: logging.Logger | None = None,
    raise_on_failure: bool = False,
    **kwargs: Any,
) -> requests.Response | None:
    """Send ``requests.<method>(url)``, retrying transport errors.

    After a failed attempt, ``reping`` (if given) checks the forwarder again;
    when it does not answer, the remaining attempts are skipped.

    Returns:
        The response (any status code), or ``None`` if every attempt hit a
        transport error (timeout, refused, reset).

    Raises:
        requests.RequestException: The last transport error, when every
            attempt failed and ``raise_on_failure`` is set.
    """
    log = log or logger
    send = getattr(requests, method)
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return send(url, timeout=timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            last_error = e
            log.warning("OEO request %s %s failed (attempt %d/%d): %s", method.upper(), url, attempt, attempts, e)
        if attempt >= attempts:
            break
        if reping is not None and not reping():
            log.warning("OEO forwarder did not answer a re-ping; not retrying %s", url)
            break
        time.sleep(retry_delay_s)
    log.error("OEO request %s %s failed: %s", method.upper(), url, last_error)
    if raise_on_failure and last_error is not None:
        raise last_error
    return None
