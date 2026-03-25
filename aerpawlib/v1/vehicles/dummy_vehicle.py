"""Placeholder vehicle for scripts without a physical vehicle."""

from typing import Any, Optional


class DummyVehicle:
    """
    A placeholder vehicle class for scripts that do not require physical vehicle interaction.

    This class provides the same interface as `Vehicle` but with empty implementations.
    """

    def __init__(self):
        self._closed = False

    def set_event_log(self, event_log: Optional[Any]) -> None:
        """No-op: DummyVehicle ignores structured logging."""
        pass

    def close(self):
        """Mark the dummy vehicle as closed."""
        self._closed = True

    def _preflight_wait(self, should_arm):
        """No-op preflight hook for compatibility with Vehicle."""
        pass

    async def _arm_vehicle(self):
        """No-op arming hook for compatibility with Vehicle."""
        pass
