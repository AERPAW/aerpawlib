"""
.. include:: ../../docs/v2/exceptions.md
"""

from __future__ import annotations

from typing import Any, Literal

Severity = Literal["warning", "error", "critical"]


class AerpawlibError(Exception):
    """
    Base exception for all aerpawlib v2 errors.

    Attributes:
        message: Human-readable description
        code: Machine-readable error code
        severity: warning, error, or critical
        original_error: Underlying exception if any
    """

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN",
        severity: Severity = "error",
        original_error: Exception | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.severity = severity
        self.original_error = original_error
        super().__init__(message)

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} (caused by: {self.original_error})"
        return self.message


# Connection
class AerpawConnectionError(AerpawlibError):
    """Base for connection errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "CONNECTION_ERROR")
        super().__init__(message, **kwargs)


class ConnectionTimeoutError(AerpawConnectionError):
    """Connection timed out."""

    def __init__(
        self,
        timeout_seconds: float,
        message: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with the timeout duration.

        Args:
            timeout_seconds: How many seconds elapsed before the timeout.
            message: Optional custom message; defaults to a standard timeout
                description.
        """
        self.timeout_seconds = timeout_seconds
        kwargs.setdefault("code", "CONNECTION_TIMEOUT")
        msg = message or f"Connection timed out after {timeout_seconds}s"
        super().__init__(msg, **kwargs)


class HeartbeatLostError(AerpawConnectionError):
    """Vehicle heartbeat lost."""

    def __init__(
        self,
        last_heartbeat_age: float = 0.0,
        message: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with the age of the last received heartbeat.

        Args:
            last_heartbeat_age: Seconds since the last heartbeat was received.
            message: Optional custom message; defaults to a standard description.
        """
        self.last_heartbeat_age = last_heartbeat_age
        kwargs.setdefault("code", "HEARTBEAT_LOST")
        kwargs.setdefault("severity", "critical")
        msg = message or f"Heartbeat lost (last {last_heartbeat_age:.1f}s ago)"
        super().__init__(msg, **kwargs)


class PortInUseError(AerpawConnectionError):
    """Port already in use."""

    def __init__(self, port: int, message: str | None = None, **kwargs: Any) -> None:
        """Initialize with the conflicting port number.

        Args:
            port: The port number that is already in use.
            message: Optional custom message; defaults to a standard description.
        """
        self.port = port
        kwargs.setdefault("code", "PORT_IN_USE")
        msg = message or f"Port {port} is already in use"
        super().__init__(msg, **kwargs)


# Command
class CommandError(AerpawlibError):
    """Base for command execution errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "COMMAND_ERROR")
        super().__init__(message, **kwargs)


class ArmError(CommandError):
    """Raised when an arm command fails."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(f"Failed to arm: {reason}", code="ARM_ERROR", **kwargs)


class DisarmError(CommandError):
    """Raised when a disarm command fails."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(f"Failed to disarm: {reason}", code="DISARM_ERROR", **kwargs)


class TakeoffError(CommandError):
    """Raised when a takeoff command fails."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(f"Takeoff failed: {reason}", code="TAKEOFF_ERROR", **kwargs)


class LandingError(CommandError):
    """Raised when a landing command fails."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(f"Landing failed: {reason}", code="LANDING_ERROR", **kwargs)


class NavigationError(CommandError):
    """Raised when navigation to a target cannot be completed."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(
            f"Navigation failed: {reason}", code="NAVIGATION_ERROR", **kwargs,
        )


class VelocityError(CommandError):
    """Raised when a velocity command cannot be applied."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(
            f"Set velocity failed: {reason}", code="VELOCITY_ERROR", **kwargs,
        )


class RTLError(CommandError):
    """Raised when return-to-launch fails."""

    def __init__(self, reason: str = "Unknown", **kwargs: Any) -> None:
        super().__init__(f"RTL failed: {reason}", code="RTL_ERROR", **kwargs)


# State
class StateError(AerpawlibError):
    """Base for vehicle state errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "STATE_ERROR")
        super().__init__(message, **kwargs)


class NotArmableError(StateError):
    """Raised when the vehicle cannot be armed in its current state."""

    def __init__(self, reason: str = "Vehicle not armable", **kwargs: Any) -> None:
        kwargs.setdefault("code", "NOT_ARMABLE")
        super().__init__(f"Cannot arm: {reason}", **kwargs)


class NotConnectedError(StateError):
    """Raised when a command requires an active vehicle connection."""

    def __init__(self, message: str = "Vehicle not connected", **kwargs: Any) -> None:
        kwargs.setdefault("code", "NOT_CONNECTED")
        super().__init__(message, **kwargs)


# Runner
class RunnerError(AerpawlibError):
    """Base for runner/state machine errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "RUNNER_ERROR")
        super().__init__(message, **kwargs)


class NoEntrypointError(RunnerError):
    """Raised when a runner has no method marked with ``@entrypoint``."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("code", "NO_ENTRYPOINT")
        super().__init__("No @entrypoint declared", **kwargs)


class InvalidStateError(RunnerError):
    """Raised when a state machine transitions to an unknown state."""

    def __init__(
        self, state_name: str, available_states: list[str], **kwargs: Any,
    ) -> None:
        """Initialize with the invalid state name and the list of valid states.

        Args:
            state_name: The state name that was not found.
            available_states: List of valid state names for this runner.
        """
        self.state_name = state_name
        self.available_states = available_states
        kwargs.setdefault("code", "INVALID_STATE")
        super().__init__(
            f"Invalid state '{state_name}'. Available: {available_states}",
            **kwargs,
        )


class NoInitialStateError(RunnerError):
    """Raised when no state is marked as the initial state."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("code", "NO_INITIAL_STATE")
        super().__init__("No initial state", **kwargs)


class MultipleInitialStatesError(RunnerError):
    """Raised when more than one state is marked initial."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("code", "MULTIPLE_INITIAL_STATES")
        super().__init__("Multiple initial states", **kwargs)


class InvalidStateNameError(RunnerError):
    """Raised when a state decorator is given an empty name."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("code", "INVALID_STATE_NAME")
        super().__init__("State name cannot be empty", **kwargs)


class UnexpectedDisarmError(StateError):
    """Raised when the vehicle disarms unexpectedly during execution."""

    def __init__(
        self,
        message: str = "Vehicle disarmed unexpectedly during experiment",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("code", "UNEXPECTED_DISARM")
        kwargs.setdefault("severity", "critical")
        super().__init__(message, **kwargs)


class PlanError(AerpawlibError):
    """Raised when a .plan file cannot be parsed."""

    def __init__(self, message: str = "Plan file error", **kwargs: Any) -> None:
        kwargs.setdefault("code", "PLAN_ERROR")
        super().__init__(message, **kwargs)
