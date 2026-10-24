"""Pilot / failsafe / C-VM takeover detection.

On the AERPAW testbed the C-VM filter ends the experiment if the E-VM commands
the vehicle after it was taken out of GUIDED. aerpawlib stops commanding it
and raises VehicleTakenOverError instead.
"""

import asyncio

import pytest

from aerpawlib._internal.takeover import TakeoverTracker


def _flying(tracker: TakeoverTracker) -> TakeoverTracker:
    tracker.update(armed=True, mode="OFFBOARD")  # MAVSDK's name for ArduPilot GUIDED
    return tracker


def test_leaving_guided_while_armed_is_a_takeover():
    tracker = _flying(TakeoverTracker())
    assert tracker.taken_over_mode is None
    tracker.update(mode="HOLD")  # safety pilot or C-VM collision hold (LOITER)
    assert tracker.taken_over_mode == "HOLD"
    assert "HOLD" in tracker.message("goto")


def test_takeover_lasts_until_disarm_even_back_in_guided():
    tracker = _flying(TakeoverTracker())
    tracker.update(mode="HOLD")
    tracker.update(mode="OFFBOARD")
    assert tracker.taken_over_mode == "HOLD"
    tracker.update(armed=False)
    assert tracker.taken_over_mode is None


def test_modes_before_first_guided_are_not_a_takeover():
    """Arming happens in another mode before aerpawlib switches to GUIDED."""
    tracker = TakeoverTracker()
    tracker.update(armed=True, mode="HOLD")
    assert tracker.taken_over_mode is None


def test_own_land_is_not_a_takeover_but_a_pilot_land_is():
    ours = _flying(TakeoverTracker())
    ours.note_land()
    ours.update(mode="LAND")
    assert ours.taken_over_mode is None

    pilot = _flying(TakeoverTracker())
    pilot.update(mode="LAND")
    assert pilot.taken_over_mode == "LAND"


def test_disarmed_vehicle_is_never_taken_over():
    tracker = TakeoverTracker()
    tracker.update(armed=False, mode="OFFBOARD")
    tracker.update(mode="HOLD")
    assert tracker.taken_over_mode is None


def _vehicle(api: str, monkeypatch, on_aerpaw: bool):
    from tests.unit.test_velocity import _recording_system, _vehicle

    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, "drone", monkeypatch, system)
    monkeypatch.setattr(type(vehicle), "_must_avoid_loiter", lambda _self: on_aerpaw)
    _flying(vehicle._takeover)
    return vehicle, vector_cls, sent


def _error_cls(api: str):
    if api == "v1":
        from aerpawlib.v1.exceptions import VehicleTakenOverError
    else:
        from aerpawlib.v2.exceptions import VehicleTakenOverError
    return VehicleTakenOverError


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_set_velocity_after_takeover_raises_and_sends_nothing(api, monkeypatch):
    vehicle, vector_cls, sent = _vehicle(api, monkeypatch, on_aerpaw=True)
    vehicle._takeover.update(mode="HOLD")
    with pytest.raises(_error_cls(api)):
        await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_running_stream_goes_quiet_after_takeover(api, monkeypatch):
    """No more setpoints and no stop setpoint: either would end the experiment."""
    vehicle, vector_cls, sent = _vehicle(api, monkeypatch, on_aerpaw=True)
    await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    await asyncio.sleep(0.12)
    assert sent
    vehicle._takeover.update(mode="HOLD")
    count = len(sent)
    await asyncio.sleep(0.3)
    assert len(sent) == count
    assert not vehicle._velocity.active


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_await_ready_to_move_raises_after_takeover(api, monkeypatch):
    vehicle, _, _ = _vehicle(api, monkeypatch, on_aerpaw=True)
    del vehicle.await_ready_to_move  # the helper stubs it; use the real one
    vehicle._takeover.update(mode="HOLD")
    with pytest.raises(_error_cls(api)):
        await vehicle.await_ready_to_move()


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_outside_aerpaw_commands_still_go_through(api, monkeypatch):
    vehicle, vector_cls, sent = _vehicle(api, monkeypatch, on_aerpaw=False)
    vehicle._takeover.update(mode="HOLD")
    await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0), duration=0.1)
    await asyncio.sleep(0.2)
    assert sent
