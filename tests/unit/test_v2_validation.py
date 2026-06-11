"""Unit tests for aerpawlib v2 preflight validation."""

from __future__ import annotations

import pytest

from aerpawlib.v2.constants import GPS_3D_FIX_TYPE
from aerpawlib.v2.safety import NoOpSafetyChecker
from aerpawlib.v2.safety.validation import PreflightChecks
from aerpawlib.v2.testing import MockVehicle
from aerpawlib.v2.types import Coordinate


class TestPreflightChecks:
    def test_check_gps_fix_passes_with_3d_fix(self):
        vehicle = MockVehicle()
        assert PreflightChecks.check_gps_fix(vehicle) is True

    def test_check_gps_fix_fails_without_3d_fix(self):
        vehicle = MockVehicle()
        vehicle._state.update_gps(2, 5)
        assert PreflightChecks.check_gps_fix(vehicle) is False

    def test_check_battery_passes_above_threshold(self):
        vehicle = MockVehicle()
        assert PreflightChecks.check_battery(vehicle, min_percent=10.0) is True

    def test_check_battery_fails_below_threshold(self):
        vehicle = MockVehicle()
        vehicle._state.update_battery(11.0, 0.0, 5.0)
        assert PreflightChecks.check_battery(vehicle, min_percent=10.0) is False

    @pytest.mark.asyncio
    async def test_run_all_passes(self):
        vehicle = MockVehicle()
        assert await PreflightChecks.run_all(vehicle) is True

    @pytest.mark.asyncio
    async def test_run_all_fails_on_low_battery(self):
        vehicle = MockVehicle()
        vehicle._state.update_battery(11.0, 0.0, 5.0)
        assert await PreflightChecks.run_all(vehicle) is False


class TestCanTakeoff:
    @pytest.mark.asyncio
    async def test_can_takeoff_passes_on_healthy_mock(self):
        vehicle = MockVehicle()
        vehicle.safety = NoOpSafetyChecker("test")
        ok, msg = await vehicle.can_takeoff(10.0)
        assert ok is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_can_takeoff_fails_when_not_armable(self):
        vehicle = MockVehicle()
        vehicle._state.update_armable(
            global_ok=False,
            local_ok=False,
            home_ok=False,
            armable=False,
        )
        ok, msg = await vehicle.can_takeoff(10.0)
        assert ok is False
        assert "not armable" in msg.lower()

    @pytest.mark.asyncio
    async def test_can_takeoff_fails_without_gps_fix(self):
        vehicle = MockVehicle()
        vehicle._state.update_gps(2, 4)
        ok, msg = await vehicle.can_takeoff(10.0)
        assert ok is False
        assert str(GPS_3D_FIX_TYPE) in msg or "gps" in msg.lower()

    @pytest.mark.asyncio
    async def test_can_goto_rejects_invalid_tolerance(self):
        vehicle = MockVehicle()
        target = Coordinate(35.73, -78.69, 10.0)
        ok, msg = await vehicle.can_goto(target, tolerance=0.01)
        assert ok is False
        assert "tolerance" in msg.lower()

    @pytest.mark.asyncio
    async def test_can_goto_passes_with_valid_tolerance(self):
        vehicle = MockVehicle()
        vehicle.safety = NoOpSafetyChecker("test")
        target = Coordinate(35.73, -78.69, 10.0)
        ok, msg = await vehicle.can_goto(target, tolerance=3.0)
        assert ok is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_can_land_passes_with_noop_safety(self):
        vehicle = MockVehicle()
        vehicle.safety = NoOpSafetyChecker("test")
        ok, msg = await vehicle.can_land()
        assert ok is True
        assert msg == ""
