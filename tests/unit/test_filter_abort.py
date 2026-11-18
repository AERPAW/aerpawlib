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


@pytest.mark.asyncio
async def test_a_hanging_safety_checker_does_not_delay_the_disconnect():
    """An unreachable checker (dead C-VM) must not hold HeartbeatLostError
    past the timeout; the hanging request is cancelled."""
    cancelled = []

    async def hangs():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    state = ConnectionState(link_alive=True)
    started = time.monotonic()
    future = state.watch_disconnect(0.5, start_delay=0, check_interval=0.01, abort_reason=hangs)
    try:
        with contextlib.suppress(HeartbeatLostError):
            await asyncio.wait_for(asyncio.shield(future), timeout=3)
        elapsed = time.monotonic() - started
    finally:
        state.mark_closed()
    assert type(future.exception()) is HeartbeatLostError
    assert elapsed < 0.5 + 0.25
    assert cancelled


@pytest.mark.asyncio
async def test_a_reason_within_the_timeout_still_ends_the_watch_with_it():
    async def slow_reason():
        await asyncio.sleep(0.1)
        return "Vehicle taken over: mode LOITER"

    state = ConnectionState(link_alive=True)
    future = state.watch_disconnect(0.5, start_delay=0, check_interval=0.01, abort_reason=slow_reason)
    try:
        with contextlib.suppress(HeartbeatLostError):
            await asyncio.wait_for(asyncio.shield(future), timeout=3)
    finally:
        state.mark_closed()
    err = future.exception()
    assert isinstance(err, FilterAbortedError)
    assert err.reason.startswith("Vehicle taken over")


@pytest.mark.asyncio
async def test_a_short_timeout_still_asks_once_past_it(monkeypatch):
    """--heartbeat-timeout 3.5 s with the 1 s check interval: the watch can
    first see the stale link with age already past the timeout. It still
    asks once, so the filter's reason is not lost."""
    from aerpawlib.v2 import constants

    monkeypatch.setattr("aerpawlib.v2.vehicle.connection_state.FILTER_STATUS_CHECK_AFTER_S", constants.FILTER_STATUS_CHECK_AFTER_S)
    monkeypatch.setattr("aerpawlib.v2.vehicle.connection_state.FILTER_STATUS_POLL_INTERVAL_S", constants.FILTER_STATUS_POLL_INTERVAL_S)
    asked = []

    async def reason():
        asked.append(time.monotonic())
        return "Vehicle taken over: mode LOITER"

    state = ConnectionState(link_alive=True)
    future = state.watch_disconnect(3.5, start_delay=0, check_interval=1.0, abort_reason=reason)
    # Checks then see ages of about 0.5, 1.5, 2.5 and 3.5 s.
    state.last_telemetry_at = time.monotonic() - 0.5
    try:
        with contextlib.suppress(HeartbeatLostError):
            await asyncio.wait_for(asyncio.shield(future), timeout=6)
    finally:
        state.mark_closed()
    assert isinstance(future.exception(), FilterAbortedError)
    assert len(asked) == 1


@pytest.mark.asyncio
async def test_a_hanging_late_ask_delays_the_disconnect_by_its_budget_at_most():
    from aerpawlib.v2.constants import FILTER_STATUS_LATE_ASK_TIMEOUT_S

    cancelled = []

    async def hangs():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    state = ConnectionState(link_alive=True)
    future = state.watch_disconnect(0.5, start_delay=0, check_interval=0.01, abort_reason=hangs)
    state.last_telemetry_at = time.monotonic() - 1.0  # already past the timeout
    started = time.monotonic()
    try:
        with contextlib.suppress(HeartbeatLostError):
            await asyncio.wait_for(asyncio.shield(future), timeout=5)
        elapsed = time.monotonic() - started
    finally:
        state.mark_closed()
    assert type(future.exception()) is HeartbeatLostError
    assert cancelled  # it did ask
    assert elapsed < FILTER_STATUS_LATE_ASK_TIMEOUT_S + 0.25


@pytest.mark.asyncio
async def test_the_late_ask_is_made_again_after_telemetry_resumes():
    """Asking in one outage must not suppress the late ask in the next."""
    answers = [None, "geofence breach"]

    async def reason():
        return answers.pop(0)

    state = ConnectionState(link_alive=True)
    future = state.watch_disconnect(0.5, start_delay=0, check_interval=0.3, abort_reason=reason)
    state.last_telemetry_at = time.monotonic() - 0.1  # first outage: asked, no reason
    try:
        await asyncio.sleep(0.1)
        assert answers == ["geofence breach"]
        # Telemetry resumed, then stopped long enough ago that the next check
        # already sees the link past the timeout.
        state.last_telemetry_at = time.monotonic() - 1.0
        with contextlib.suppress(HeartbeatLostError):
            await asyncio.wait_for(asyncio.shield(future), timeout=3)
    finally:
        state.mark_closed()
    err = future.exception()
    assert isinstance(err, FilterAbortedError)
    assert err.reason == "geofence breach"
