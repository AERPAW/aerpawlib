"""
Placeholder vehicle implementation for v1.

This module provides `DummyVehicle`, a no-op compatibility class for examples
and tests that do not need a live MAVSDK vehicle connection.

Capabilities
- Provide a minimal vehicle-like interface for non-flight code paths.
- Allow runner and helper code to execute without hardware/SITL dependencies.
"""

from typing import Any, Optional


class DummyVehicle:
    """
    A placeholder vehicle class for scripts that do not require physical vehicle interaction.

    This class provides the same interface as `Vehicle` but with empty implementations.
    """

    def __init__(self) -> None:
        self._closed = False

    def set_event_log(self, event_log: Optional[Any]) -> None:
        """No-op: DummyVehicle ignores structured logging."""
        pass

    def close(self) -> None:
        """Mark the dummy vehicle as closed."""
        self._closed = True

    def _preflight_wait(self, should_arm: bool) -> None:
        """No-op preflight hook for compatibility with Vehicle."""
        pass

    async def _arm_vehicle(self) -> None:
        """No-op arming hook for compatibility with Vehicle."""
        pass
