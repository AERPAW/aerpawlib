"""Unit tests for aerpawlib v1 helpers module."""

import asyncio

import pytest

from aerpawlib.v1.helpers import (
    heading_difference,
    normalize_heading,
    validate_altitude,
    validate_speed,
    validate_tolerance,
    wait_for_condition,
    wait_for_value_change,
)
from aerpawlib.v1.constants import (
    MIN_POSITION_TOLERANCE_M,
    MAX_POSITION_TOLERANCE_M,
    MIN_FLIGHT_ALTITUDE_M,
    MAX_ALTITUDE_M,
    MIN_GROUNDSPEED_M_S,
    MAX_GROUNDSPEED_M_S,
)


class TestWaitForCondition:
    """wait_for_condition and wait_for_value_change."""

    @pytest.mark.asyncio
    async def test_condition_met_immediately(self):
        result = await wait_for_condition(lambda: True, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_condition_met_after_delay(self):
        state = {"count": 0}

        def cond():
            state["count"] += 1
            return state["count"] >= 3

        await wait_for_condition(cond, timeout=5.0, poll_interval=0.01)
        assert state["count"] >= 3

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        with pytest.raises(TimeoutError):
            await wait_for_condition(
                lambda: False,
                timeout=0.1,
                poll_interval=0.01,
                timeout_message="Operation timed out",
            )

    @pytest.mark.asyncio
    async def test_wait_for_value_change(self):
        state = {"val": 0}

        async def setter():
            await asyncio.sleep(0.05)
            state["val"] = 42

        asyncio.create_task(setter())
        result = await wait_for_value_change(
            lambda: state["val"], 42, timeout=1.0, poll_interval=0.01
        )
        assert result == 42


class TestValidateTolerance:
    """validate_tolerance."""

    def test_valid(self):
        assert validate_tolerance(1.0) == 1.0
        assert validate_tolerance(MIN_POSITION_TOLERANCE_M) == MIN_POSITION_TOLERANCE_M
        assert validate_tolerance(MAX_POSITION_TOLERANCE_M) == MAX_POSITION_TOLERANCE_M

    def test_too_small_raises(self):
        with pytest.raises(ValueError, match="at least"):
            validate_tolerance(0.05)

    def test_too_large_raises(self):
        with pytest.raises(ValueError, match="at most"):
            validate_tolerance(150)


class TestValidateAltitude:
    """validate_altitude."""

    def test_valid(self):
        assert validate_altitude(10.0) == 10.0
        assert validate_altitude(MIN_FLIGHT_ALTITUDE_M) == MIN_FLIGHT_ALTITUDE_M
        assert validate_altitude(MAX_ALTITUDE_M) == MAX_ALTITUDE_M

    def test_too_low_raises(self):
        with pytest.raises(ValueError, match="at least"):
            validate_altitude(0.5)

    def test_too_high_raises(self):
        with pytest.raises(ValueError, match="at most"):
            validate_altitude(500)


class TestValidateSpeed:
    """validate_speed."""

    def test_valid(self):
        assert validate_speed(5.0) == 5.0
        assert validate_speed(MIN_GROUNDSPEED_M_S) == MIN_GROUNDSPEED_M_S
        assert validate_speed(MAX_GROUNDSPEED_M_S) == MAX_GROUNDSPEED_M_S

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="at least"):
            validate_speed(-1.0)

    def test_too_high_raises(self):
        with pytest.raises(ValueError, match="at most"):
            validate_speed(50.0)


class TestNormalizeHeading:
    """normalize_heading."""

    def test_already_normalized(self):
        assert normalize_heading(90) == 90
        assert normalize_heading(0) == 0

    def test_wraps_negative(self):
        assert normalize_heading(-90) == 270

    def test_wraps_over_360(self):
        assert normalize_heading(450) == 90


class TestHeadingDifference:
    """heading_difference."""

    def test_same_heading(self):
        assert heading_difference(90, 90) == 0

    def test_180_apart(self):
        assert heading_difference(0, 180) == 180

    def test_wraps_correctly(self):
        assert heading_difference(350, 10) == 20
