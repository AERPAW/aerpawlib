"""Private connection lifecycle state for v1 vehicles."""

from __future__ import annotations

from aerpawlib.v1.helpers import ThreadSafeValue


class ConnectionLifecycle:
    """Tracks heartbeat, closed flag, and background-loop running state."""

    def __init__(self) -> None:
        self.has_heartbeat: bool = False
        self.closed: bool = False
        self._running = ThreadSafeValue(initial_value=True)

    def is_running(self) -> bool:
        """Return True while background MAVSDK/telemetry loops should run."""
        return self._running.get()

    def stop(self) -> None:
        """Signal background loops to exit."""
        self._running.set(False)

    def mark_closed(self) -> None:
        """Mark session closed and stop heartbeat tracking."""
        if self.closed:
            return
        self.closed = True
        self.has_heartbeat = False
        self.stop()
