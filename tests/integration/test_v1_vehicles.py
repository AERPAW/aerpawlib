"""Integration tests for v1 Vehicle base and DummyVehicle (no SITL required)."""

import pytest

from aerpawlib.v1.vehicle import DummyVehicle


class TestDummyVehicle:
    """DummyVehicle for testing without SITL."""

    def test_creates(self):
        v = DummyVehicle()
        assert v is not None

    def test_close_noop(self):
        v = DummyVehicle()
        v.close()

    def test_initialize_prearm_noop(self):
        v = DummyVehicle()
        v._initialize_prearm(should_postarm_init=True)

    @pytest.mark.asyncio
    async def test_initialize_postarm_noop(self):
        v = DummyVehicle()
        await v._initialize_postarm()
