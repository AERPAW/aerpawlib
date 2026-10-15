"""Rover set_velocity streams GUIDED setpoints and never uses MAVSDK offboard.

MAVSDK offboard.stop() switches ArduRover to HOLD, which the AERPAW C-VM
filter treats as fatal (the rover allow-list has GUIDED only), so rover
velocity control must start and stop without a mode change.
"""

import asyncio
import json
import math
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymavlink import mavutil

from aerpawlib.v1.util import VectorNED as V1VectorNED
from aerpawlib.v2.types import VectorNED as V2VectorNED

IGNORE_VELOCITY = 0b111000
# C-VM filter POSITION_TYPEMASK_CHECK: position and acceleration must be ignored.
FILTER_MASK = 0b000111000111
HEADING_DEG = 90.0
FIRST = (1.0, 2.0, 3.0)
SECOND = (0.0, -2.0, 0.0)


def _recording_system() -> tuple[MagicMock, list]:
    sent: list = []
    system = MagicMock()
    system.sysid = 1

    async def send_message(msg):
        sent.append((msg.message_name, json.loads(msg.fields_json)))

    system.mavlink_direct.send_message = AsyncMock(side_effect=send_message)
    return system, sent


def _is_stop(fields: dict) -> bool:
    return fields["type_mask"] & IGNORE_VELOCITY == IGNORE_VELOCITY


def _ready():
    async def ready():
        return None

    return ready


def _rover(api: str, monkeypatch, system):
    if api == "v1":
        from aerpawlib.v1.vehicle.rover import Rover

        vehicle = Rover.__new__(Rover)
        vehicle._velocity_generation = 0
        vehicle._velocity_active = False
        vehicle._event_log = None
        vehicle._command_tasks = []
        vehicle._system = system

        async def _direct(coro):
            return await coro

        vehicle._run_on_mavsdk_loop = _direct
        vector_cls = V1VectorNED
    else:
        from aerpawlib.v2.vehicle.rover import Rover

        vehicle = Rover(system, "udpin://127.0.0.1:14550")
        vector_cls = V2VectorNED
    vehicle.await_ready_to_move = _ready()
    monkeypatch.setattr(Rover, "heading", property(lambda _self: HEADING_DEG))
    # On the testbed: the path that used to raise VelocityError.
    monkeypatch.setattr(Rover, "_must_avoid_loiter", lambda _self: True)
    return vehicle, vector_cls


async def _wait_for_stop(sent: list) -> None:
    for _ in range(100):
        if any(_is_stop(f) for _, f in sent):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"no stop setpoint sent: {sent}")


def _cancel(vehicle) -> None:
    for task in vehicle._command_tasks:
        task.cancel()


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_rover_velocity_streams_then_stops_in_guided(api, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _rover(api, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST), duration=0.2)
    await asyncio.sleep(0.5)

    names = {name for name, _ in sent}
    # No COMMAND_LONG: no DO_SET_MODE, so the rover never leaves GUIDED.
    assert names == {"SET_POSITION_TARGET_LOCAL_NED"}, sent
    assert system.offboard.method_calls == []
    for _, fields in sent:
        assert fields["type_mask"] & FILTER_MASK == FILTER_MASK, fields
        assert fields["coordinate_frame"] == mavutil.mavlink.MAV_FRAME_LOCAL_NED

    velocity = [f for _, f in sent if not _is_stop(f)]
    assert len(velocity) > 1, "setpoint must be resent so ArduRover does not time out"
    assert all((f["vx"], f["vy"], f["vz"]) == (FIRST[0], FIRST[1], 0.0) for f in velocity)

    stops = [f for _, f in sent if _is_stop(f)]
    assert len(stops) == 1, sent
    assert _is_stop(sent[-1][1])
    # Speed 0 at the current heading, not a zero vector (which steers north).
    assert stops[0]["yaw"] == pytest.approx(math.radians(HEADING_DEG))
    _cancel(vehicle)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_rover_expiring_velocity_does_not_stop_newer_command(api, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _rover(api, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST), duration=0.05)
    await _wait_for_stop(sent)
    await vehicle.set_velocity(vector_cls(*SECOND))
    await asyncio.sleep(0.4)

    last_second = max(i for i, (_, f) in enumerate(sent) if not _is_stop(f) and (f["vx"], f["vy"]) == SECOND[:2])
    assert not any(_is_stop(f) for _, f in sent[last_second:]), sent
    _cancel(vehicle)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_rover_stop_ends_velocity_once(api, monkeypatch):
    """A following movement command (via _stop) ends the stream in GUIDED."""
    system, sent = _recording_system()
    vehicle, vector_cls = _rover(api, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.2)
    await vehicle._stop()
    await asyncio.sleep(0.2)
    await vehicle._stop()

    assert _is_stop(sent[-1][1]), sent
    assert sum(_is_stop(f) for _, f in sent) == 1, sent
    assert system.offboard.method_calls == []
    _cancel(vehicle)
