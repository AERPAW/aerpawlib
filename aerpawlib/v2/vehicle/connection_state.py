"""Single authority for vehicle connection lifecycle and disconnect monitoring."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aerpawlib.v2.constants import (
    FILTER_STATUS_CHECK_AFTER_S,
    FILTER_STATUS_POLL_INTERVAL_S,
    HEARTBEAT_CHECK_INTERVAL_S,
    HEARTBEAT_START_DELAY_S,
)
from aerpawlib.v2.exceptions import FilterAbortedError, HeartbeatLostError
from aerpawlib.v2.log import LogComponent, get_logger

logger = get_logger(LogComponent.VEHICLE)


@dataclass
class ConnectionState:
    """Tracks MAVLink link state, telemetry freshness, and shutdown lifecycle."""

    link_alive: bool = False
    last_telemetry_at: float = 0.0
    closed: bool = False
    _disconnect_future: asyncio.Future | None = field(default=None, repr=False)
    _monitor_task: asyncio.Task | None = field(default=None, repr=False)
    _on_disconnect: Callable[[], None] | None = field(default=None, repr=False)
    _abort_reason: Callable[[], Awaitable[str | None]] | None = field(default=None, repr=False)

    @property
    def connected(self) -> bool:
        """True when the link is alive and the vehicle session is not closed."""
        return self.link_alive and not self.closed

    def record_telemetry(self) -> None:
        """Record receipt of telemetry (heartbeat activity)."""
        self.last_telemetry_at = time.monotonic()

    def set_link_alive(self, alive: bool) -> None:
        """Update MAVSDK connection_state link status."""
        self.link_alive = alive

    def mark_closed(self) -> None:
        """Mark the session closed and stop disconnect monitoring."""
        self.closed = True
        self.link_alive = False
        self._stop_monitor()

    def watch_disconnect(
        self,
        timeout: float,
        *,
        start_delay: float = HEARTBEAT_START_DELAY_S,
        check_interval: float = HEARTBEAT_CHECK_INTERVAL_S,
        on_disconnect: Callable[[], None] | None = None,
        abort_reason: Callable[[], Awaitable[str | None]] | None = None,
    ) -> asyncio.Future:
        """Start monitoring telemetry staleness; return a Future that completes on loss.

        Args:
            timeout: Seconds without telemetry before disconnect is signalled.
            start_delay: Grace period before the first timeout check.
            check_interval: Poll interval for the monitor loop.
            on_disconnect: Optional callback invoked when heartbeat is lost.
            abort_reason: Optional coroutine function returning why the C-VM
                filter cut the link, or None. Asked once telemetry is
                FILTER_STATUS_CHECK_AFTER_S stale; a reason ends the watch
                at once instead of after ``timeout``.

        Returns:
            asyncio.Future completed with HeartbeatLostError on disconnect, or
            FilterAbortedError when the filter reported why it cut the link.
        """
        self._stop_monitor()
        self._on_disconnect = on_disconnect
        self._abort_reason = abort_reason
        loop = asyncio.get_running_loop()
        self._disconnect_future = loop.create_future()
        self.last_telemetry_at = time.monotonic()
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(timeout, start_delay, check_interval),
        )
        logger.info(
            f"ConnectionState: disconnect watch started (timeout={timeout}s, start_delay={start_delay}s)",
        )
        return self._disconnect_future

    def _stop_monitor(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            self._monitor_task = None

    async def _monitor_loop(
        self,
        timeout: float,
        start_delay: float,
        check_interval: float,
    ) -> None:
        try:
            await asyncio.sleep(start_delay)
            next_reason_check = 0.0
            while not self.closed:
                age = time.monotonic() - self.last_telemetry_at
                reason = None
                if self._abort_reason is not None and age > FILTER_STATUS_CHECK_AFTER_S and time.monotonic() >= next_reason_check:
                    next_reason_check = time.monotonic() + FILTER_STATUS_POLL_INTERVAL_S
                    try:
                        reason = await self._abort_reason()
                    except Exception as e:
                        logger.debug(f"ConnectionState: could not ask why the link is down: {e}")
                if reason is not None or age > timeout:
                    await self._signal_disconnect(age, reason)
                    return
                await asyncio.sleep(check_interval)
        except asyncio.CancelledError:
            return

    async def _signal_disconnect(self, age: float, reason: str | None) -> None:
        if reason is not None:
            logger.error(f"C-VM filter ended the experiment (last telemetry {age:.1f}s ago): {reason}")
            err: HeartbeatLostError = FilterAbortedError(reason, last_heartbeat_age=age)
        else:
            logger.error(f"Heartbeat lost (last telemetry {age:.1f}s ago)")
            err = HeartbeatLostError(last_heartbeat_age=age)
        if self._on_disconnect is not None:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, self._on_disconnect)
            except Exception as e:
                logger.warning(
                    f"ConnectionState: on_disconnect callback raised: {e}",
                )
        if self._disconnect_future and not self._disconnect_future.done():
            with contextlib.suppress(asyncio.InvalidStateError):
                self._disconnect_future.set_exception(err)
