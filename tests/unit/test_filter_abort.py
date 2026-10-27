"""v2 learns why the C-VM filter cut the link, from the safety checker."""

import asyncio
import contextlib
import time

import pytest

from aerpawlib.v2.exceptions import FilterAbortedError, HeartbeatLostError
from aerpawlib.v2.vehicle.connection_state import ConnectionState


@pytest.fixture(autouse=True)
def _fast_checks(monkeypatch):
    monkeypatch.setattr("aerpawlib.v2.vehicle.connection_state.FILTER_STATUS_CHECK_AFTER_S", 0.05)
    monkeypatch.setattr("aerpawlib.v2.vehicle.connection_state.FILTER_STATUS_POLL_INTERVAL_S", 0.05)


async def _watch(abort_reason, timeout=30.0):
    state = ConnectionState(link_alive=True)
    future = state.watch_disconnect(timeout, start_delay=0, check_interval=0.01, abort_reason=abort_reason)
    state.last_telemetry_at = time.monotonic() - 1.0  # telemetry already stale
    try:
        with contextlib.suppress(HeartbeatLostError):
            await asyncio.wait_for(asyncio.shield(future), timeout=2)
        return future
    finally:
        state.mark_closed()


@pytest.mark.asyncio
async def test_reported_abort_ends_the_watch_at_once_with_the_reason():
    async def reason():
        return "Velocity setpoint would leave the geofence within 4s."

    future = await _watch(reason)
    err = future.exception()
    assert isinstance(err, FilterAbortedError)
    assert isinstance(err, HeartbeatLostError)  # existing handlers still catch it
    assert "geofence" in str(err)
    assert err.reason.startswith("Velocity setpoint")


@pytest.mark.asyncio
async def test_without_a_reason_the_watch_waits_for_the_timeout():
    async def no_reason():
        return None

    future = await _watch(no_reason, timeout=1.2)
    assert type(future.exception()) is HeartbeatLostError


@pytest.mark.asyncio
async def test_a_failing_safety_checker_does_not_stop_the_watch():
    async def broken():
        raise TimeoutError("no reply")

    future = await _watch(broken, timeout=1.2)
    assert type(future.exception()) is HeartbeatLostError


@pytest.mark.asyncio
async def test_fresh_telemetry_never_asks():
    asked = []

    async def reason():
        asked.append(True)
        return "should not be asked"

    state = ConnectionState(link_alive=True)
    future = state.watch_disconnect(30, start_delay=0, check_interval=0.01, abort_reason=reason)
    for _ in range(20):
        state.record_telemetry()
        await asyncio.sleep(0.01)
    state.mark_closed()
    assert asked == []
    assert not future.done()


@pytest.mark.asyncio
async def test_vehicle_filter_abort_reason_asks_the_safety_checker():
    from unittest.mock import MagicMock

    from aerpawlib.v2.vehicle.drone import Drone

    class _Checker:
        def __init__(self, status):
            self.status = status

        async def get_filter_status(self):
            return self.status

    drone = Drone(MagicMock(), "udpin://127.0.0.1:14550")
    assert await drone.filter_abort_reason() is None  # no safety checker
    drone.safety = _Checker(None)  # server can't say
    assert await drone.filter_abort_reason() is None
    drone.safety = _Checker({"aborted": False, "reason": None})
    assert await drone.filter_abort_reason() is None
    drone.safety = _Checker({"aborted": True, "reason": "Mode 5 not allowed."})
    assert await drone.filter_abort_reason() == "Mode 5 not allowed."
