"""Integration tests for aerpawlib v2 safety: PreflightChecks, command validation. Requires SITL."""

import pytest

pytestmark = [pytest.mark.integration]


class TestPreflightChecks:
    """PreflightChecks.run_all."""

    @pytest.mark.asyncio
    async def test_run_all_passes_with_gps(self, connected_drone_v2):
        from aerpawlib.v2.safety import PreflightChecks

        await connected_drone_v2._preflight_wait(should_arm=True)
        ok = await PreflightChecks.run_all(connected_drone_v2)
        assert ok is True


class TestCommandValidation:
    """can_takeoff, can_goto, can_land (no SafetyCheckerClient)."""

    @pytest.mark.asyncio
    async def test_can_takeoff_passes_when_armable(self, connected_drone_v2):
        await connected_drone_v2._preflight_wait(should_arm=True)
        ok, msg = await connected_drone_v2.can_takeoff(10)
        assert ok is True, msg

    @pytest.mark.asyncio
    async def test_can_goto_passes_with_valid_target(self, connected_drone_v2):
        from aerpawlib.v2.types import VectorNED

        await connected_drone_v2._preflight_wait(should_arm=True)
        target = connected_drone_v2.position + VectorNED(20, 0, 0)
        ok, msg = await connected_drone_v2.can_goto(target)
        assert ok is True, msg

    @pytest.mark.asyncio
    async def test_can_land_passes_without_safety_client(self, connected_drone_v2):
        ok, msg = await connected_drone_v2.can_land()
        assert ok is True, msg
