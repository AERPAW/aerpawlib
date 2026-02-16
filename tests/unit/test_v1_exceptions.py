"""Unit tests for aerpawlib v1 exception hierarchy."""

import pytest

from aerpawlib.v1.exceptions import (
    AerpawConnectionError,
    AerpawlibError,
    ConnectionTimeoutError,
    ArmError,
    DisarmError,
    NotArmableError,
    TakeoffError,
    NavigationError,
    StateMachineError,
)


class TestAerpawlibError:
    """Base exception and hierarchy."""

    def test_base_message(self):
        e = AerpawlibError("test message")
        assert str(e) == "test message"
        assert e.message == "test message"

    def test_with_original_error(self):
        e = AerpawlibError("outer", original_error=ValueError("inner"))
        assert "caused by" in str(e)
        assert "inner" in str(e)


class TestConnectionErrors:
    """Connection-related exceptions."""

    def test_connection_timeout(self):
        e = ConnectionTimeoutError(30.0)
        assert "30" in str(e)
        assert e.timeout_seconds == 30.0

    def test_aerpaw_connection_inherits(self):
        assert issubclass(ConnectionTimeoutError, AerpawConnectionError)
        assert issubclass(ConnectionTimeoutError, AerpawlibError)


class TestActionErrors:
    """Arm, disarm, takeoff errors."""

    def test_arm_error(self):
        e = ArmError("failed")
        assert "failed" in str(e)

    def test_disarm_error(self):
        e = DisarmError("failed")
        assert "failed" in str(e)

    def test_not_armable_error(self):
        e = NotArmableError("not ready")
        assert "not ready" in str(e)

    def test_takeoff_error(self):
        e = TakeoffError("rejected")
        assert "rejected" in str(e)
        assert issubclass(TakeoffError, AerpawlibError)

    def test_navigation_error(self):
        e = NavigationError("timeout")
        assert "timeout" in str(e)


class TestStateMachineError:
    """StateMachineError."""

    def test_state_machine_error(self):
        e = StateMachineError("invalid state")
        assert "invalid state" in str(e)
