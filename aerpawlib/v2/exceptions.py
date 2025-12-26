"""
Exception hierarchy for aerpawlib v2 API.

This module provides a structured set of exceptions for granular error handling
in vehicle control scripts. All exceptions inherit from AerpawlibError.

Example:
    from aerpawlib.v2 import (
        Drone,
        ConnectionError,
        CommandError,
        TimeoutError,
        AbortError,
    )

    try:
        await drone.connect()
        await drone.takeoff(altitude=10)
    except ConnectionError as e:
        print(f"Failed to connect: {e}")
    except TimeoutError as e:
        print(f"Operation timed out: {e}")
    except CommandError as e:
        print(f"Command failed: {e}")
"""
from __future__ import annotations

from typing import Optional, Any, Dict
from enum import Enum, auto


class ErrorSeverity(Enum):
    """Severity level of an error."""
    WARNING = auto()      # Recoverable, operation may continue
    ERROR = auto()        # Operation failed, but vehicle is safe
    CRITICAL = auto()     # Immediate action required
    FATAL = auto()        # Unrecoverable, mission should abort


class AerpawlibError(Exception):
    """
    Base exception for all aerpawlib errors.

    Attributes:
        message: Human-readable error description
        severity: Error severity level
        details: Optional dictionary with additional context
        recoverable: Whether the error can be recovered from
    """

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.details = details or {}
        self.recoverable = recoverable

    def __str__(self) -> str:
        base = f"[{self.severity.name}] {self.message}"
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            base += f" ({detail_str})"
        return base


# Connection Errors

class ConnectionError(AerpawlibError):
    """Raised when vehicle connection fails or is lost."""

    def __init__(
        self,
        message: str,
        address: Optional[str] = None,
        timeout: Optional[float] = None,
        attempt: Optional[int] = None,
        max_attempts: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if address:
            details["address"] = address
        if timeout is not None:
            details["timeout"] = timeout
        if attempt is not None:
            details["attempt"] = attempt
        if max_attempts is not None:
            details["max_attempts"] = max_attempts

        super().__init__(message, details=details, **kwargs)
        self.address = address
        self.timeout = timeout
        self.attempt = attempt
        self.max_attempts = max_attempts


class ConnectionTimeoutError(ConnectionError):
    """Raised when connection attempt times out."""

    def __init__(
        self,
        message: str = "Connection timed out",
        timeout: float = 30.0,
        **kwargs
    ):
        super().__init__(message, timeout=timeout, **kwargs)


class HeartbeatLostError(ConnectionError):
    """Raised when heartbeat is lost from the vehicle."""

    def __init__(
        self,
        message: str = "Lost heartbeat from vehicle",
        last_heartbeat: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if last_heartbeat is not None:
            details["seconds_since_heartbeat"] = last_heartbeat

        super().__init__(message, severity=ErrorSeverity.CRITICAL, details=details, **kwargs)
        self.last_heartbeat = last_heartbeat


class ReconnectionError(ConnectionError):
    """Raised when automatic reconnection fails."""

    def __init__(
        self,
        message: str = "Failed to reconnect to vehicle",
        **kwargs
    ):
        super().__init__(message, recoverable=False, **kwargs)


# Command Errors

class CommandError(AerpawlibError):
    """Raised when a vehicle command fails."""

    def __init__(
        self,
        message: str,
        command: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if command:
            details["command"] = command
        if reason:
            details["reason"] = reason

        super().__init__(message, details=details, **kwargs)
        self.command = command
        self.reason = reason


class ArmError(CommandError):
    """Raised when arming fails."""

    def __init__(
        self,
        message: str = "Failed to arm vehicle",
        reason: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, command="arm", reason=reason, **kwargs)


class DisarmError(CommandError):
    """Raised when disarming fails."""

    def __init__(
        self,
        message: str = "Failed to disarm vehicle",
        reason: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, command="disarm", reason=reason, **kwargs)


class TakeoffError(CommandError):
    """Raised when takeoff fails."""

    def __init__(
        self,
        message: str = "Takeoff failed",
        target_altitude: Optional[float] = None,
        current_altitude: Optional[float] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target_altitude is not None:
            details["target_altitude"] = target_altitude
        if current_altitude is not None:
            details["current_altitude"] = current_altitude

        super().__init__(message, command="takeoff", reason=reason, details=details, **kwargs)
        self.target_altitude = target_altitude
        self.current_altitude = current_altitude


class LandingError(CommandError):
    """Raised when landing fails."""

    def __init__(
        self,
        message: str = "Landing failed",
        current_altitude: Optional[float] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if current_altitude is not None:
            details["current_altitude"] = current_altitude

        super().__init__(
            message,
            command="land",
            reason=reason,
            severity=ErrorSeverity.CRITICAL,
            details=details,
            **kwargs
        )
        self.current_altitude = current_altitude


class NavigationError(CommandError):
    """Raised when a navigation command fails (goto, move, etc.)."""

    def __init__(
        self,
        message: str = "Navigation command failed",
        target: Optional[Any] = None,
        current_position: Optional[Any] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target is not None:
            details["target"] = str(target)
        if current_position is not None:
            details["current_position"] = str(current_position)

        super().__init__(message, command="goto", reason=reason, details=details, **kwargs)
        self.target = target
        self.current_position = current_position


class ModeChangeError(CommandError):
    """Raised when changing flight mode fails."""

    def __init__(
        self,
        message: str = "Failed to change flight mode",
        target_mode: Optional[str] = None,
        current_mode: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target_mode:
            details["target_mode"] = target_mode
        if current_mode:
            details["current_mode"] = current_mode

        super().__init__(message, command="set_mode", reason=reason, details=details, **kwargs)
        self.target_mode = target_mode
        self.current_mode = current_mode


class OffboardError(CommandError):
    """Raised when offboard mode operations fail."""

    def __init__(
        self,
        message: str = "Offboard mode operation failed",
        reason: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, command="offboard", reason=reason, **kwargs)


# Timeout Errors

class TimeoutError(AerpawlibError):
    """Raised when an operation times out."""

    def __init__(
        self,
        message: str = "Operation timed out",
        operation: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if operation:
            details["operation"] = operation
        if timeout is not None:
            details["timeout_seconds"] = timeout

        super().__init__(message, details=details, **kwargs)
        self.operation = operation
        self.timeout = timeout


class GotoTimeoutError(TimeoutError):
    """Raised when goto operation times out."""

    def __init__(
        self,
        message: str = "Goto operation timed out",
        target: Optional[Any] = None,
        distance_remaining: Optional[float] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target is not None:
            details["target"] = str(target)
        if distance_remaining is not None:
            details["distance_remaining"] = distance_remaining

        super().__init__(message, operation="goto", timeout=timeout, details=details, **kwargs)
        self.target = target
        self.distance_remaining = distance_remaining


class TakeoffTimeoutError(TimeoutError):
    """Raised when takeoff times out."""

    def __init__(
        self,
        message: str = "Takeoff timed out",
        target_altitude: Optional[float] = None,
        current_altitude: Optional[float] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target_altitude is not None:
            details["target_altitude"] = target_altitude
        if current_altitude is not None:
            details["current_altitude"] = current_altitude

        super().__init__(message, operation="takeoff", timeout=timeout, details=details, **kwargs)
        self.target_altitude = target_altitude
        self.current_altitude = current_altitude


class LandingTimeoutError(TimeoutError):
    """Raised when landing times out."""

    def __init__(
        self,
        message: str = "Landing timed out",
        current_altitude: Optional[float] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if current_altitude is not None:
            details["current_altitude"] = current_altitude

        super().__init__(
            message,
            operation="land",
            timeout=timeout,
            severity=ErrorSeverity.CRITICAL,
            details=details,
            **kwargs
        )
        self.current_altitude = current_altitude


# Abort Errors

class AbortError(AerpawlibError):
    """Raised when an operation is aborted."""

    def __init__(
        self,
        message: str = "Operation aborted",
        operation: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if operation:
            details["operation"] = operation
        if reason:
            details["reason"] = reason

        super().__init__(message, details=details, recoverable=True, **kwargs)
        self.operation = operation
        self.reason = reason


class UserAbortError(AbortError):
    """Raised when user explicitly aborts an operation."""

    def __init__(
        self,
        message: str = "User aborted operation",
        **kwargs
    ):
        super().__init__(message, reason="user_request", **kwargs)


class CommandCancelledError(AbortError):
    """Raised when a command is explicitly cancelled via its handle."""

    def __init__(
        self,
        message: str = "Command was cancelled",
        command: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if command:
            details["command"] = command

        super().__init__(message, reason="cancelled", details=details, **kwargs)
        self.command = command


class SafetyAbortError(AbortError):
    """Raised when safety system triggers an abort."""

    def __init__(
        self,
        message: str = "Safety system triggered abort",
        violation: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if violation:
            details["violation"] = violation

        super().__init__(
            message,
            reason="safety_violation",
            severity=ErrorSeverity.CRITICAL,
            details=details,
            **kwargs
        )
        self.violation = violation


# Safety Errors

class SafetyError(AerpawlibError):
    """Base class for safety-related errors."""

    def __init__(self, message: str, violation: Optional[Any] = None, **kwargs):
        super().__init__(message, severity=ErrorSeverity.WARNING, **kwargs)
        self.violation = violation


class GeofenceViolationError(SafetyError):
    """Raised when a command would violate geofence constraints."""

    def __init__(
        self,
        message: str = "Command would violate geofence",
        violation: Optional[Any] = None,
        current_position: Optional[Any] = None,
        target_position: Optional[Any] = None,
        geofence_name: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if current_position is not None:
            details["current_position"] = str(current_position)
        if target_position is not None:
            details["target_position"] = str(target_position)
        if geofence_name:
            details["geofence"] = geofence_name

        super().__init__(message, violation=violation, details=details, **kwargs)
        self.current_position = current_position
        self.target_position = target_position
        self.geofence_name = geofence_name


class AltitudeViolationError(SafetyError):
    """Raised when a command would violate altitude constraints."""

    def __init__(
        self,
        message: str = "Command would violate altitude limits",
        target_altitude: Optional[float] = None,
        min_altitude: Optional[float] = None,
        max_altitude: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target_altitude is not None:
            details["target_altitude"] = target_altitude
        if min_altitude is not None:
            details["min_altitude"] = min_altitude
        if max_altitude is not None:
            details["max_altitude"] = max_altitude

        super().__init__(message, details=details, **kwargs)
        self.target_altitude = target_altitude
        self.min_altitude = min_altitude
        self.max_altitude = max_altitude


class SpeedViolationError(SafetyError):
    """Raised when a command would violate speed constraints."""

    def __init__(
        self,
        message: str = "Command would violate speed limits",
        violation: Optional[Any] = None,
        requested_speed: Optional[float] = None,
        max_speed: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if requested_speed is not None:
            details["requested_speed"] = requested_speed
        if max_speed is not None:
            details["max_speed"] = max_speed

        super().__init__(message, violation=violation, details=details, **kwargs)
        self.requested_speed = requested_speed
        self.max_speed = max_speed


class SpeedLimitExceededError(SafetyError):
    """Raised when a speed limit would be exceeded."""

    def __init__(
        self,
        message: str = "Speed limit exceeded",
        violation: Optional[Any] = None,
        value: Optional[float] = None,
        limit: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if value is not None:
            details["value"] = value
        if limit is not None:
            details["limit"] = limit

        super().__init__(message, violation=violation, details=details, **kwargs)
        self.value = value
        self.limit = limit


class ParameterValidationError(SafetyError):
    """Raised when a command parameter is invalid."""

    def __init__(
        self,
        message: str = "Invalid parameter",
        violation: Optional[Any] = None,
        parameter: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if parameter is not None:
            details["parameter"] = parameter
        if value is not None:
            details["value"] = str(value)

        super().__init__(message, violation=violation, details=details, **kwargs)
        self.parameter = parameter
        self.value = value


# Pre-flight Errors

class PreflightError(AerpawlibError):
    """Raised when pre-flight checks fail."""

    def __init__(
        self,
        message: str = "Pre-flight check failed",
        check_name: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if check_name:
            details["check"] = check_name
        if reason:
            details["reason"] = reason

        super().__init__(message, details=details, **kwargs)
        self.check_name = check_name
        self.reason = reason


class PreflightCheckError(PreflightError):
    """Raised when pre-flight safety checks fail (from safety module)."""

    def __init__(
        self,
        message: str = "Pre-flight checks failed",
        result: Optional[Any] = None,
        violation: Optional[Any] = None,
        **kwargs
    ):
        # Extract failed checks from result if available
        failed_checks = []
        if result is not None and hasattr(result, 'failed_checks'):
            failed_checks = result.failed_checks
            if not message or message == "Pre-flight checks failed":
                message = f"Pre-flight checks failed: {', '.join(failed_checks)}"

        details = kwargs.pop("details", {})
        if failed_checks:
            details["failed_checks"] = failed_checks

        super().__init__(message, details=details, **kwargs)
        self.result = result
        self.violation = violation


class GPSError(PreflightError):
    """Raised when GPS is not ready."""

    def __init__(
        self,
        message: str = "GPS not ready",
        satellites: Optional[int] = None,
        fix_type: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if satellites is not None:
            details["satellites"] = satellites
        if fix_type is not None:
            details["fix_type"] = fix_type

        super().__init__(message, check_name="gps", details=details, **kwargs)
        self.satellites = satellites
        self.fix_type = fix_type


class BatteryError(PreflightError):
    """Raised when battery level is insufficient."""

    def __init__(
        self,
        message: str = "Battery level too low",
        percentage: Optional[float] = None,
        minimum_required: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if percentage is not None:
            details["percentage"] = percentage
        if minimum_required is not None:
            details["minimum_required"] = minimum_required

        super().__init__(message, check_name="battery", details=details, **kwargs)
        self.percentage = percentage
        self.minimum_required = minimum_required


class NotArmableError(PreflightError):
    """Raised when vehicle is not ready to arm."""

    def __init__(
        self,
        message: str = "Vehicle is not ready to arm",
        reasons: Optional[list] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if reasons:
            details["reasons"] = reasons

        super().__init__(message, check_name="armable", details=details, **kwargs)
        self.reasons = reasons or []


# State Machine Errors

class StateMachineError(AerpawlibError):
    """Base class for state machine related errors."""

    def __init__(
        self,
        message: str,
        current_state: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if current_state:
            details["current_state"] = current_state

        super().__init__(message, details=details, **kwargs)
        self.current_state = current_state


class InvalidStateError(StateMachineError):
    """Raised when transitioning to an invalid state."""

    def __init__(
        self,
        message: str = "Invalid state transition",
        target_state: Optional[str] = None,
        available_states: Optional[list] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if target_state:
            details["target_state"] = target_state
        if available_states:
            details["available_states"] = available_states

        super().__init__(message, details=details, **kwargs)
        self.target_state = target_state
        self.available_states = available_states or []


class NoInitialStateError(StateMachineError):
    """Raised when no initial state is defined."""

    def __init__(
        self,
        message: str = "No initial state defined",
        **kwargs
    ):
        super().__init__(message, recoverable=False, **kwargs)


class MultipleInitialStatesError(StateMachineError):
    """Raised when multiple initial states are defined."""

    def __init__(
        self,
        message: str = "Multiple initial states defined",
        states: Optional[list] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if states:
            details["initial_states"] = states

        super().__init__(message, recoverable=False, details=details, **kwargs)
        self.states = states or []


# Exports
__all__ = [
    # Base
    "AerpawlibError",
    "ErrorSeverity",
    # Connection
    "ConnectionError",
    "ConnectionTimeoutError",
    "HeartbeatLostError",
    "ReconnectionError",
    # Command
    "CommandError",
    "ArmError",
    "DisarmError",
    "TakeoffError",
    "LandingError",
    "NavigationError",
    "ModeChangeError",
    "OffboardError",
    # Timeout
    "TimeoutError",
    "GotoTimeoutError",
    "TakeoffTimeoutError",
    "LandingTimeoutError",
    # Abort
    "AbortError",
    "UserAbortError",
    "CommandCancelledError",
    "SafetyAbortError",
    # Safety
    "SafetyError",
    "GeofenceViolationError",
    "AltitudeViolationError",
    "SpeedViolationError",
    "SpeedLimitExceededError",
    "ParameterValidationError",
    # Pre-flight
    "PreflightError",
    "PreflightCheckError",
    "GPSError",
    "BatteryError",
    "NotArmableError",
    # State Machine
    "StateMachineError",
    "InvalidStateError",
    "NoInitialStateError",
    "MultipleInitialStatesError",
]

