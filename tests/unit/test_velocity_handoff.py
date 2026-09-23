"""Regression tests: an expiring timed set_velocity must not stop a newer one.

A velocity loop whose ``duration`` elapses sends a zero setpoint, waits a
settle delay, then calls ``offboard.stop()``. If the script issues a new
``set_velocity`` during that settle delay, the stale loop used to stop
offboard *after* the new command had started it, cutting the new command off.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from aerpawlib.v1.util import VectorNED as V1VectorNED
from aerpawlib.v2.types import VectorNED as V2VectorNED

FIRST = (1.0, 0.0, 0.0)
SECOND = (0.0, 2.0, 0.0)


def _recording_offboard(zero_sent: asyncio.Event) -> tuple[MagicMock, list]:
    """Offboard mock that records calls in order and flags the first zero setpoint."""
    calls: list = []
    offboard = MagicMock()

    async def set_velocity_ned(v):
        calls.append(("set", (v.north_m_s, v.east_m_s, v.down_m_s)))
        if (v.north_m_s, v.east_m_s, v.down_m_s) == (0, 0, 0):
            zero_sent.set()

    async def start():
        calls.append(("start",))

    async def stop():
        calls.append(("stop",))

    offboard.set_velocity_ned = AsyncMock(side_effect=set_velocity_ned)
    offboard.start = AsyncMock(side_effect=start)
    offboard.stop = AsyncMock(side_effect=stop)
    return offboard, calls


def _assert_second_command_survives(calls: list) -> None:
    last_second = max(i for i, c in enumerate(calls) if c == ("set", SECOND))
    tail = calls[last_second:]
    assert ("stop",) not in tail, f"stale loop stopped offboard after new command: {calls}"
    assert not any(c[0] == "set" and c[1] == (0, 0, 0) for c in tail), calls


async def _run_handoff(vehicle, vector_cls, zero_sent: asyncio.Event) -> None:
    await vehicle.set_velocity(vector_cls(*FIRST), duration=0.05)
    # The first loop has sent its zero setpoint and is now in its settle delay.
    await asyncio.wait_for(zero_sent.wait(), timeout=2.0)
    await vehicle.set_velocity(vector_cls(*SECOND))
    await asyncio.sleep(0.4)
    for task in vehicle._command_tasks:
        task.cancel()


def _v1_vehicle(cls, monkeypatch, offboard):
    vehicle = cls.__new__(cls)
    vehicle._velocity_generation = 0
    vehicle._offboard_active = False
    vehicle._current_heading = None
    vehicle._event_log = None
    vehicle._command_tasks = []
    vehicle._system = MagicMock()
    vehicle._system.offboard = offboard

    async def _direct(coro):
        return await coro

    async def _ready():
        return None

    vehicle._run_on_mavsdk_loop = _direct
    vehicle.await_ready_to_move = _ready
    monkeypatch.setattr(cls, "heading", property(lambda _self: 0.0))
    return vehicle


def _v2_vehicle(cls, offboard):
    system = MagicMock()
    system.offboard = offboard
    vehicle = cls(system, "udpin://127.0.0.1:14550")

    async def _ready():
        return None

    vehicle.await_ready_to_move = _ready
    return vehicle


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["drone", "rover"])
async def test_v1_expiring_velocity_does_not_stop_newer_command(kind, monkeypatch):
    from aerpawlib.v1.vehicle.drone import Drone
    from aerpawlib.v1.vehicle.rover import Rover

    zero_sent = asyncio.Event()
    offboard, calls = _recording_offboard(zero_sent)
    cls = Drone if kind == "drone" else Rover
    vehicle = _v1_vehicle(cls, monkeypatch, offboard)

    await _run_handoff(vehicle, V1VectorNED, zero_sent)
    _assert_second_command_survives(calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["drone", "rover"])
async def test_v2_expiring_velocity_does_not_stop_newer_command(kind):
    from aerpawlib.v2.vehicle.drone import Drone
    from aerpawlib.v2.vehicle.rover import Rover

    zero_sent = asyncio.Event()
    offboard, calls = _recording_offboard(zero_sent)
    vehicle = _v2_vehicle(Drone if kind == "drone" else Rover, offboard)

    await _run_handoff(vehicle, V2VectorNED, zero_sent)
    _assert_second_command_survives(calls)


@pytest.mark.asyncio
async def test_v2_drone_zero_duration_stops_immediately():
    """duration=0 means stop right away, not hold forever."""
    from aerpawlib.v2.vehicle.drone import Drone

    zero_sent = asyncio.Event()
    offboard, calls = _recording_offboard(zero_sent)
    vehicle = _v2_vehicle(Drone, offboard)

    await vehicle.set_velocity(V2VectorNED(*FIRST), duration=0)
    await asyncio.wait_for(zero_sent.wait(), timeout=1.0)
    await asyncio.sleep(0.2)
    assert calls[-1] == ("stop",), calls
