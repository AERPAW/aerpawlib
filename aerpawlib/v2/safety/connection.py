"""Signal handler helpers for v2 CLI experiments."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable

from aerpawlib.v2.log import LogComponent, get_logger

logger = get_logger(LogComponent.VEHICLE)


def setup_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    on_sigint: Callable[[], None] | None = None,
    on_sigterm: Callable[[], None] | None = None,
) -> None:
    """Register async-safe SIGINT and SIGTERM handlers on the event loop.

    Uses loop.add_signal_handler instead of signal.signal to avoid raising
    exceptions from synchronous signal handlers and breaking the async loop.

    Args:
        loop: The running asyncio event loop to register handlers on.
        on_sigint: Optional zero-argument callback invoked on SIGINT (Ctrl-C).
        on_sigterm: Optional zero-argument callback invoked on SIGTERM.
    """
    try:
        if on_sigint:

            def _sigint():
                """Invoke the configured SIGINT callback."""
                if on_sigint:
                    on_sigint()

            loop.add_signal_handler(signal.SIGINT, _sigint)
        if on_sigterm:

            def _sigterm():
                """Invoke the configured SIGTERM callback."""
                if on_sigterm:
                    on_sigterm()

            loop.add_signal_handler(signal.SIGTERM, _sigterm)
    except NotImplementedError:
        logger.debug("add_signal_handler not available on this platform")
    else:
        logger.debug("Signal handlers (SIGINT, SIGTERM) registered")
