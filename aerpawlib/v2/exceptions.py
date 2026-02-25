"""
Exceptions for aerpawlib v2 API.

Structured hierarchy with error codes and severity.
"""

from __future__ import annotations

from typing import Literal, Optional

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
        original_error: Optional[Exception] = None,
    ):
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

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("code", "CONNECTION_ERROR")
        super().__init__(message, **kwargs)


class ConnectionTimeoutError(AerpawConnectionError):
    """Connection timed out."""

    def __init__(self, timeout_seconds: float, message: Optional[str] = None):
        self.timeout_seconds = timeout_seconds
        msg = message or f"Connection timed out after {timeout_seconds}s"
        super().__init__(msg, code="CONNECTION_TIMEOUT")


class HeartbeatLostError(AerpawConnectionError):
    """Vehicle heartbeat lost."""

    def __init__(self, last_heartbeat_age: float = 0.0, message: Optional[str] = None):
        self.last_heartbeat_age = last_heartbeat_age
        msg = message or f"Heartbeat lost (last {last_heartbeat_age:.1f}s ago)"
        super().__init__(msg, code="HEARTBEAT_LOST", severity="critical")


class PortInUseError(AerpawConnectionError):
    """Port already in use."""

    def __init__(self, port: int, message: Optional[str] = None):
        self.port = port
        msg = message or f"Port {port} is already in use"
        super().__init__(msg, code="PORT_IN_USE")


# Command
class CommandError(AerpawlibError):
    """Base for command execution errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("code", "COMMAND_ERROR")
        super().__init__(message, **kwargs)


class ArmError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"Failed to arm: {reason}", code="ARM_ERROR", **kwargs)


class DisarmError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"Failed to disarm: {reason}", code="DISARM_ERROR", **kwargs)


class TakeoffError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"Takeoff failed: {reason}", code="TAKEOFF_ERROR", **kwargs)


class LandingError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"Landing failed: {reason}", code="LANDING_ERROR", **kwargs)


class NavigationError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"Navigation failed: {reason}", code="NAVIGATION_ERROR", **kwargs)


class VelocityError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"Set velocity failed: {reason}", code="VELOCITY_ERROR", **kwargs)


class RTLError(CommandError):
    def __init__(self, reason: str = "Unknown", **kwargs):
        super().__init__(f"RTL failed: {reason}", code="RTL_ERROR", **kwargs)


# State
class StateError(AerpawlibError):
    """Base for vehicle state errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("code", "STATE_ERROR")
        super().__init__(message, **kwargs)


class NotArmableError(StateError):
    def __init__(self, reason: str = "Vehicle not armable"):
        super().__init__(f"Cannot arm: {reason}", code="NOT_ARMABLE")


class NotConnectedError(StateError):
    def __init__(self, message: str = "Vehicle not connected"):
        super().__init__(message, code="NOT_CONNECTED")


# Runner
class RunnerError(AerpawlibError):
    """Base for runner/state machine errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("code", "RUNNER_ERROR")
        super().__init__(message, **kwargs)


class NoEntrypointError(RunnerError):
    def __init__(self):
        super().__init__("No @entrypoint declared", code="NO_ENTRYPOINT")


class InvalidStateError(RunnerError):
    def __init__(self, state_name: str, available_states: list):
        self.state_name = state_name
        self.available_states = available_states
        super().__init__(
            f"Invalid state '{state_name}'. Available: {available_states}",
            code="INVALID_STATE",
        )


class NoInitialStateError(RunnerError):
    def __init__(self):
        super().__init__("No initial state", code="NO_INITIAL_STATE")


class MultipleInitialStatesError(RunnerError):
    def __init__(self):
        super().__init__("Multiple initial states", code="MULTIPLE_INITIAL_STATES")


class InvalidStateNameError(RunnerError):
    def __init__(self):
        super().__init__("State name cannot be empty", code="INVALID_STATE_NAME")
