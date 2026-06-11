"""Unit tests for aerpawlib v2 VehicleTask."""

from __future__ import annotations

import asyncio

import pytest

from aerpawlib.v2.exceptions import TaskCancelledError
from aerpawlib.v2.vehicle.task import VehicleTask


class TestVehicleTask:
    def test_progress_clamped(self):
        task = VehicleTask()
        task.set_progress(-0.5)
        assert task.progress == 0.0
        task.set_progress(1.5)
        assert task.progress == 1.0

    def test_set_complete_marks_done(self):
        task = VehicleTask()
        task.set_complete()
        assert task.is_done() is True

    @pytest.mark.asyncio
    async def test_wait_done_raises_on_error(self):
        task = VehicleTask()
        task.set_error(RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            await task.wait_done()

    @pytest.mark.asyncio
    async def test_cancel_without_callback(self):
        task = VehicleTask()
        task.cancel()
        assert task.is_cancelled() is True
        with pytest.raises(TaskCancelledError):
            await task.wait_done()

    @pytest.mark.asyncio
    async def test_cancel_async_runs_callback(self):
        task = VehicleTask()
        called = asyncio.Event()

        async def on_cancel() -> None:
            called.set()

        task.set_on_cancel(on_cancel)
        await task.cancel_async()
        assert called.is_set()
        assert task.is_done() is True

    @pytest.mark.asyncio
    async def test_cancel_invokes_sync_callback(self):
        task = VehicleTask()
        called = False

        def on_cancel() -> None:
            nonlocal called
            called = True

        task.set_on_cancel(on_cancel)
        task.cancel()
        await asyncio.sleep(0.05)
        assert called is True
        assert task.is_done() is True
