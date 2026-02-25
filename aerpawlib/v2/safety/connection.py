"""
ConnectionHandler for aerpawlib v2.

Single authority for connection state and heartbeat monitoring.
Starts monitoring after first telemetry or short delay.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Callable, Optional, Protocol

from ..constants import HEARTBEAT_START_DELAY_S, HEARTBEAT_TIMEOUT_S
from ..exceptions import HeartbeatLostError
from ..logging import LogComponent, get_logger
from ..protocols import VehicleProtocol

logger = get_logger(LogComponent.VEHICLE)


class ConnectionHandler:
    """
    Single authority for connection state and heartbeat.

    Protocol-based: depends on VehicleProtocol (heartbeat_tick), not concrete Vehicle.
    Start monitoring only after first telemetry or short post-connect delay.
    On disconnect: notify OEO, trigger callbacks, exit.
    """

    def __init__(
        self,
        vehicle: VehicleProtocol,
        heartbeat_timeout: float = HEARTBEAT_TIMEOUT_S,
        start_delay: float = HEARTBEAT_START_DELAY_S,
        on_disconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self._vehicle = vehicle
        self._heartbeat_timeout = heartbeat_timeout
        self._start_delay = start_delay
        self._on_disconnect = on_disconnect
        self._last_tick: float = 0.0
        self._monitor_started = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._disconnected = False

    def heartbeat_tick(self) -> None:
        """Called by vehicle when telemetry received."""
        import time

        self._last_tick = time.monotonic()
        if not self._monitor_started:
            self._monitor_started = True

    def start(self) -> None:
        """Start heartbeat monitor. Call after vehicle connects."""
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self) -> None:
        """Monitor heartbeat. Start checking after start_delay."""
        import time

        await asyncio.sleep(self._start_delay)  # Justified: avoid false "heartbeat lost"
        while not self._disconnected:
            now = time.monotonic()
            age = now - self._last_tick
            if age > self._heartbeat_timeout:
                self._disconnected = True
                logger.error(f"Heartbeat lost (last {age:.1f}s ago)")
                if self._on_disconnect:
                    self._on_disconnect()
                raise HeartbeatLostError(last_heartbeat_age=age)
            await asyncio.sleep(1.0)  # Justified: heartbeat check interval

    def stop(self) -> None:
        """Stop monitor."""
        self._disconnected = True
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None


def setup_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    on_sigint: Optional[Callable[[], None]] = None,
    on_sigterm: Optional[Callable[[], None]] = None,
) -> None:
    """
    Use loop.add_signal_handler for async-safe SIGINT/SIGTERM.
    Avoid raising from sync signal handlers.
    """
    if sys.platform == "win32":
        return
    try:
        if on_sigint:

            def _sigint():
                if on_sigint:
                    on_sigint()

            loop.add_signal_handler(signal.SIGINT, _sigint)
        if on_sigterm:

            def _sigterm():
                if on_sigterm:
                    on_sigterm()

            loop.add_signal_handler(signal.SIGTERM, _sigterm)
    except NotImplementedError:
        logger.debug("add_signal_handler not available on this platform")
