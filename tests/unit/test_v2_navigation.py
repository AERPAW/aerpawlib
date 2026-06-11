"""Unit tests for aerpawlib v2 navigation helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from aerpawlib.v2.types import Coordinate
from aerpawlib.v2.vehicle.navigation import (
    start_nonblocking_goto,
    wait_for_blocking_goto,
)


@dataclass
class _NavVehicle:
    """Minimal vehicle stub for navigation polling tests."""

    _moving: bool = True
    _command_tasks: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._command_tasks is None:
            self._command_tasks = []

    def done_moving(self) -> bool:
        return not self._moving


@pytest.mark.asyncio
async def test_wait_for_blocking_goto_completes_when_done():
    vehicle = _NavVehicle(_moving=True)
    target = Coordinate(35.72, -78.69, 10.0)

    loop = asyncio.get_running_loop()
    loop.call_later(0.05, lambda: setattr(vehicle, "_moving", False))
    await wait_for_blocking_goto(
        vehicle,  # type: ignore[arg-type]
        target,
        distance_fn=lambda: 1.0,
        tolerance=2.0,
        timeout=2.0,
        log_prefix="test: ",
    )


@pytest.mark.asyncio
async def test_wait_for_blocking_goto_times_out():
    vehicle = _NavVehicle(_moving=True)
    target = Coordinate(35.72, -78.69, 10.0)
    with pytest.raises(TimeoutError, match="timed out"):
        await wait_for_blocking_goto(
            vehicle,  # type: ignore[arg-type]
            target,
            distance_fn=lambda: 5.0,
            tolerance=2.0,
            timeout=0.05,
            log_prefix="test: ",
        )


@pytest.mark.asyncio
async def test_start_nonblocking_goto_completes():
    vehicle = _NavVehicle(_moving=True)
    target = Coordinate(35.72, -78.69, 10.0)

    loop = asyncio.get_running_loop()
    loop.call_later(0.05, lambda: setattr(vehicle, "_moving", False))
    handle = start_nonblocking_goto(
        vehicle,  # type: ignore[arg-type]
        target,
        distance_fn=lambda: 10.0,
        tolerance=2.0,
        timeout=2.0,
        on_cancel=lambda: asyncio.sleep(0),
        log_prefix="test: ",
    )
    await handle.wait_done()
    assert handle.progress == 1.0
