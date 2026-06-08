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
