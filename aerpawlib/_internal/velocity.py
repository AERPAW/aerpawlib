"""GUIDED-mode velocity streaming shared by every vehicle and API version.

MAVSDK offboard is not used: ``offboard.stop()`` switches ArduPilot to
LOITER/HOLD, which the AERPAW C-VM filter treats as fatal. Setpoints are
SET_POSITION_TARGET_LOCAL_NED sent through ``mavlink_direct`` in GUIDED, and
stopping is one more setpoint, so the vehicle never changes mode.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("aerpawlib")

Send = Callable[[Any], Awaitable[Any]]


def velocity_problem(north: float, east: float, down: float, duration: float | None) -> str | None:
    """Return why a set_velocity call is invalid, or None."""
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (north, east, down)):
        return f"velocity must be finite (got {north!r}, {east!r}, {down!r})"
    if duration is not None and not (isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0):
        return f"duration must be None or a finite number >= 0 (got {duration!r})"
    return None


async def _send_stop(send: Send | None, stop_setpoint: Callable[[], Any]) -> None:
    """Send the stop setpoint; a second cancellation of the caller can't abort it."""
    if send is None:
        return
    try:
        await asyncio.shield(send(stop_setpoint()))
    except Exception as e:
        logger.warning("velocity stop setpoint failed: %s", e)


class VelocityStream:
    """Resends one velocity setpoint until it expires, is replaced, or is stopped.

    ArduPilot drops a GUIDED velocity target after GUID_TIMEOUT (3 s) without a
    new one, so the setpoint is resent every ``interval`` seconds. Whenever
    velocity ends without a newer setpoint taking over (duration reached, send
    error, cancellation at any point), the vehicle's stop setpoint is sent.
    """

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._task: asyncio.Task | None = None
        # Bumped when the running stream is replaced or stopped by the vehicle,
        # so the stream knows not to send its own stop setpoint.
        self._generation = 0
        # Serializes start/stop so overlapping calls can't leave two streams.
        self._lock = asyncio.Lock()

    @property
    def active(self) -> bool:
        """True while a stream is running (including its final stop setpoint)."""
        return self._task is not None and not self._task.done()

    async def start(
        self,
        send: Send,
        setpoint: Any,
        stop_setpoint: Callable[[], Any],
        duration: float | None,
    ) -> asyncio.Task:
        """Send ``setpoint`` now and keep resending it in the background.

        Replaces a running stream without stopping the vehicle in between.
        Raises whatever ``send`` raises for the first setpoint, after sending
        the stop setpoint.
        """
        async with self._lock:
            await self._end(send, stop_setpoint)
            try:
                await send(setpoint)
            except BaseException:
                # The old stream is gone and this one never started.
                await _send_stop(send, stop_setpoint)
                raise
            end = None if duration is None else time.monotonic() + duration
            self._task = asyncio.create_task(self._run(self._generation, send, setpoint, stop_setpoint, end))
            return self._task

    async def stop(self, send: Send | None, stop_setpoint: Callable[[], Any]) -> None:
        """End the stream and send the stop setpoint; no-op if nothing is streaming.

        ``send`` None ends the stream without sending (vehicle closed).
        """
        async with self._lock:
            if await self._end(send, stop_setpoint):
                await _send_stop(send, stop_setpoint)

    def forget(self) -> None:
        """Make the running stream exit silently when it is cancelled.

        For sync close paths that send the stop setpoint themselves.
        """
        self._generation += 1

    async def _end(self, send: Send | None, stop_setpoint: Callable[[], Any]) -> bool:
        """Cancel the running stream without its stop setpoint.

        Returns True if a stream was running. If the caller is cancelled while
        waiting for it, nothing else will stop the vehicle, so this does.
        """
        self._generation += 1
        task, self._task = self._task, None
        if task is None or task.done():
            return False
        task.cancel()
        try:
            # wait() doesn't raise the task's CancelledError, only the caller's.
            await asyncio.wait({task})
        except BaseException:
            await _send_stop(send, stop_setpoint)
            raise
        return True

    async def _run(
        self,
        generation: int,
        send: Send,
        setpoint: Any,
        stop_setpoint: Callable[[], Any],
        end: float | None,
    ) -> None:
        try:
            while end is None or time.monotonic() < end:
                delay = self._interval if end is None else min(self._interval, end - time.monotonic())
                await asyncio.sleep(max(delay, 0.0))
                if end is not None and time.monotonic() >= end:
                    break
                await send(setpoint)
        except asyncio.CancelledError:
            if self._generation == generation:
                # Cancelled from outside (vehicle close, runner shutdown):
                # don't leave the vehicle flying the last setpoint.
                await _send_stop(send, stop_setpoint)
            raise
        except Exception as e:
            logger.error("velocity stream stopped after a send error: %s", e)
        if self._generation == generation:
            await _send_stop(send, stop_setpoint)
