"""VehicleTask handle for non-blocking commands."""

from __future__ import annotations

import asyncio
from typing import Callable, List, Optional

from ..log import LogComponent, get_logger

logger = get_logger(LogComponent.VEHICLE)


class VehicleTask:
    """
    Handle for non-blocking commands with progress and cancellation.

    Use event-driven completion via position/landed_state subscriptions.
    """

    def __init__(self) -> None:
        self._done = asyncio.Event()
        self._cancelled = False
        self._progress: float = 0.0
        self._error: Optional[Exception] = None
        self._on_cancel: Optional[Callable[[], object]] = None
        self._cancel_tasks: List[asyncio.Task] = []

    @property
    def progress(self) -> float:
        """Progress 0.0 to 1.0."""
        return self._progress

    def is_done(self) -> bool:
        """True if the command has completed (success, error, or cancelled)."""
        return self._done.is_set()

    def set_progress(self, value: float) -> None:
        """Update progress (0.0-1.0). Internal use by command implementation."""
        self._progress = max(0.0, min(1.0, value))

    def set_complete(self) -> None:
        """Mark command as successfully complete. Internal use."""
        self._error = None
        self._done.set()

    def set_error(self, error: Exception) -> None:
        """Mark command as failed with error. Internal use."""
        self._error = error
        self._done.set()

    def set_on_cancel(self, callback: Callable[[], object]) -> None:
        """Set async callback to run when cancel() is called (e.g. RTL to stop goto)."""
        self._on_cancel = callback

    def cancel(self) -> None:
        """Request cancellation. Invokes on_cancel callback if set to stop the vehicle."""
        logger.debug("VehicleTask: cancel requested")
        self._cancelled = True
        if self._on_cancel:
            try:
                loop = asyncio.get_running_loop()
                result = self._on_cancel()
                if asyncio.iscoroutine(result):
                    t = loop.create_task(result)
                    self._cancel_tasks.append(t)
            except RuntimeError:
                logger.warning(
                    "VehicleTask.cancel() called outside an async context; "
                    "on_cancel callback will not run. The vehicle may continue its current task."
                )

    def is_cancelled(self) -> bool:
        """Return True if cancel() has been called."""
        return self._cancelled

    async def wait_done(self) -> None:
        """Wait until command completes or is cancelled."""
        await self._done.wait()
        if self._error is not None:
            raise self._error
