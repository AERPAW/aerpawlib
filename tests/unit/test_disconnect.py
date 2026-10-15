"""Unit tests for CLI disconnect monitoring."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from aerpawlib.cli.disconnect import (
    run_runner_with_disconnect_guard,
    wait_for_v1_connection_loss,
)
from aerpawlib.v1.exceptions import HeartbeatLostError


class _FakeVehicle:
    def __init__(self, *, connected: bool = True, closed: bool = False) -> None:
        self.connected = connected
        self._closed = closed
        self._connection_error = None


@pytest.mark.asyncio
async def test_wait_for_v1_connection_loss_keeps_monitoring_while_connected():
    """Monitor must not exit immediately when the vehicle is connected."""
    vehicle = _FakeVehicle(connected=True, closed=False)
    monitor = asyncio.create_task(
        wait_for_v1_connection_loss(
            vehicle=vehicle,
            heartbeat_timeout=60.0,
            heartbeat_error_cls=HeartbeatLostError,
        ),
    )
    await asyncio.sleep(0.05)
    assert not monitor.done()
    vehicle._closed = True
    await asyncio.wait_for(monitor, timeout=1.0)


@pytest.mark.asyncio
async def test_wait_for_v1_connection_loss_raises_after_disconnect_timeout():
    vehicle = _FakeVehicle(connected=False, closed=False)
    with pytest.raises(HeartbeatLostError):
        await wait_for_v1_connection_loss(
            vehicle=vehicle,
            heartbeat_timeout=0.02,
            heartbeat_error_cls=HeartbeatLostError,
        )


@pytest.mark.asyncio
async def test_run_runner_with_disconnect_guard_lets_runner_finish_when_connected():
    """Connected vehicle: runner must complete; disconnect must not win the race."""
    completed = False

    class Runner:
        async def run(self, vehicle: Any) -> None:
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

    vehicle = _FakeVehicle(connected=True, closed=False)
    disconnect_task = asyncio.create_task(
        wait_for_v1_connection_loss(
            vehicle=vehicle,
            heartbeat_timeout=60.0,
            heartbeat_error_cls=HeartbeatLostError,
        ),
    )
    await run_runner_with_disconnect_guard(
        runner=Runner(),
        vehicle=vehicle,
        disconnect_future=disconnect_task,
    )
    assert completed
    disconnect_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await disconnect_task


@pytest.mark.asyncio
async def test_return_home_if_armed_skips_when_closed():
    from aerpawlib.cli.constants import VEHICLE_TYPE_DRONE
    from aerpawlib.cli.rtl import return_home_if_armed

    class ClosedArmed:
        closed = True
        armed = True

        async def return_to_launch(self) -> None:
            raise AssertionError("RTL must not run after aclose")

    await return_home_if_armed(ClosedArmed(), VEHICLE_TYPE_DRONE, True, reason="test")


@pytest.mark.asyncio
async def test_return_home_if_armed_rtl_when_open_and_armed():
    from aerpawlib.cli.constants import VEHICLE_TYPE_DRONE
    from aerpawlib.cli.rtl import return_home_if_armed

    called: list[int] = []

    class OpenArmed:
        closed = False
        armed = True

        async def return_to_launch(self) -> None:
            called.append(1)

    await return_home_if_armed(OpenArmed(), VEHICLE_TYPE_DRONE, True, reason="test")
    assert called == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_disconnect_future", [True, False])
async def test_cancelling_guard_stops_runner_before_returning(with_disconnect_future):
    """SIGINT/SIGTERM cancels the guard; the runner must be stopped (and its
    cleanup run) before the guard returns and the CLI closes the vehicle."""
    order: list[str] = []
    entered = asyncio.Event()

    class Runner:
        async def run(self, vehicle: Any) -> None:
            try:
                entered.set()
                await asyncio.sleep(30)
            finally:
                await asyncio.sleep(0)  # cleanup that awaits, like v2 background gather
                order.append("runner_cleanup")

    disconnect_future = asyncio.get_running_loop().create_future() if with_disconnect_future else None
    guard = asyncio.create_task(
        run_runner_with_disconnect_guard(
            runner=Runner(),
            vehicle=_FakeVehicle(),
            disconnect_future=disconnect_future,
        ),
    )
    await entered.wait()
    guard.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await guard
    order.append("cli_would_close_vehicle_now")
    assert order == ["runner_cleanup", "cli_would_close_vehicle_now"]
    others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    assert others == []
