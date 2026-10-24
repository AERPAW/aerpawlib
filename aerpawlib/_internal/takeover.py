"""Detect that someone else has taken an armed vehicle out of GUIDED.

On the AERPAW testbed the C-VM filter ends the experiment if the E-VM commands
the vehicle after a safety pilot, a failsafe, or the C-VM collision hold has
taken it out of GUIDED. aerpawlib stops commanding it and raises instead, so a
script gets a clear error rather than a cut link.
"""

from __future__ import annotations

import threading

# MAVSDK reports ArduPilot GUIDED as OFFBOARD.
GUIDED_MODE_NAMES = frozenset({"GUIDED", "OFFBOARD"})
LAND_MODE_NAME = "LAND"


class TakeoverTracker:
    """Follows armed state and flight mode from telemetry.

    A takeover is an armed vehicle that has been in GUIDED and then reports any
    other mode, except a LAND that aerpawlib itself asked for. It lasts until
    the vehicle disarms, matching the C-VM filter's lockout.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._armed = False
        self._mode = ""
        self._guided_since_arm = False
        self._land_requested = False
        self._taken_over_mode: str | None = None

    def update(self, *, armed: bool | None = None, mode: str | None = None) -> None:
        """Record a telemetry sample (either field may be omitted)."""
        with self._lock:
            if armed is not None:
                self._armed = armed
            if mode is not None:
                self._mode = mode
            if not self._armed:
                self._guided_since_arm = False
                self._land_requested = False
                self._taken_over_mode = None
            elif self._mode in GUIDED_MODE_NAMES:
                self._guided_since_arm = True
            elif self._guided_since_arm and self._taken_over_mode is None:
                if not (self._mode == LAND_MODE_NAME and self._land_requested):
                    self._taken_over_mode = self._mode

    def note_land(self) -> None:
        """aerpawlib is about to command LAND; that LAND is not a takeover."""
        with self._lock:
            self._land_requested = True

    @property
    def taken_over_mode(self) -> str | None:
        """Mode the vehicle was taken into, or None if it has not been taken over."""
        with self._lock:
            return self._taken_over_mode

    def message(self, action: str) -> str:
        """Explain why ``action`` was refused."""
        return f"Cannot {action}: the vehicle left GUIDED for {self.taken_over_mode} while armed, so the safety pilot, a failsafe, or the C-VM collision hold has taken control. aerpawlib will not command it again until it disarms."
