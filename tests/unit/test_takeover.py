"""Pilot / failsafe / C-VM takeover, as the safety checker reports it.

On the AERPAW testbed the C-VM filter ends the experiment if the E-VM commands
the vehicle after it was taken out of GUIDED. The filter reports the takeover
to the safety checker; aerpawlib asks the checker before each GUIDED command
and raises VehicleTakenOverError instead of sending.
"""

import asyncio

import pytest

from aerpawlib.v1.constants import TAKEN_OVER_MESSAGE


class _Checker:
    """Fake safety checker: refuses everything once taken over, and can
    refuse velocities on its own (a geofence look-ahead, say)."""

    def __init__(self):
        self.taken_over = False
        self.velocity_refusal: str | None = None
        self.velocity_checks = 0

    def _guided(self):
        return (False, f"{TAKEN_OVER_MESSAGE} mode LOITER") if self.taken_over else (True, "")

    def _velocity(self):
        self.velocity_checks += 1
        ok, msg = self._guided()
        if not ok:
            return ok, msg
        return (False, self.velocity_refusal) if self.velocity_refusal else (True, "")


class _SyncChecker(_Checker):
    def validate_guided_command(self):
        return self._guided()

    def validate_velocity_command(self, _current, _velocity):
        return self._velocity()


class _AsyncChecker(_Checker):
    async def validate_guided_command(self):
        return self._guided()

    async def validate_velocity(self, _current, _velocity):
        return self._velocity()


def _vehicle(api: str, monkeypatch):
    from tests.unit.test_velocity import _recording_system, _vehicle

    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, "drone", monkeypatch, system)
    checker = _SyncChecker() if api == "v1" else _AsyncChecker()
    vehicle.safety = checker
    if api == "v1":
        from aerpawlib.v1.util import Coordinate

        monkeypatch.setattr(type(vehicle), "position", property(lambda _self: Coordinate(35.73, -78.695, 30)))
    return vehicle, vector_cls, sent, checker


def _errors(api: str):
    if api == "v1":
        from aerpawlib.v1.exceptions import VehicleTakenOverError, VelocityError
    else:
        from aerpawlib.v2.exceptions import VehicleTakenOverError, VelocityError
    return VehicleTakenOverError, VelocityError


def _fast_revalidation(api: str, monkeypatch):
    module = "aerpawlib.v1.vehicle.core_vehicle" if api == "v1" else "aerpawlib.v2.vehicle.base"
    monkeypatch.setattr(f"{module}.VELOCITY_REVALIDATE_INTERVAL_S", 0.05)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_set_velocity_after_takeover_raises_and_sends_nothing(api, monkeypatch):
    vehicle, vector_cls, sent, checker = _vehicle(api, monkeypatch)
    checker.taken_over = True
    taken_over, _ = _errors(api)
    with pytest.raises(taken_over):
        await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_running_stream_goes_quiet_after_takeover(api, monkeypatch):
    """No more setpoints and no stop setpoint: either would end the experiment."""
    vehicle, vector_cls, sent, checker = _vehicle(api, monkeypatch)
    await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    await asyncio.sleep(0.12)
    assert sent
    checker.taken_over = True
    await asyncio.sleep(0.1)
    count = len(sent)
    await asyncio.sleep(0.3)
    assert len(sent) == count
    assert not vehicle._velocity.active


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_velocity_the_checker_refuses_raises_and_sends_nothing(api, monkeypatch):
    vehicle, vector_cls, sent, checker = _vehicle(api, monkeypatch)
    checker.velocity_refusal = "Velocity setpoint would leave the geofence within 4s."
    _, velocity_error = _errors(api)
    with pytest.raises(velocity_error, match="geofence"):
        await vehicle.set_velocity(vector_cls(5.0, 0.0, 0.0))
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_running_stream_stops_when_revalidation_fails(api, monkeypatch):
    """The look-ahead moves with the vehicle: a later refusal stops it in GUIDED."""
    from tests.unit.test_velocity import _wait_for_stop

    _fast_revalidation(api, monkeypatch)
    vehicle, vector_cls, sent, checker = _vehicle(api, monkeypatch)
    await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    await asyncio.sleep(0.12)
    assert checker.velocity_checks >= 2
    checker.velocity_refusal = "Velocity setpoint would leave the geofence within 4s."
    await _wait_for_stop("drone", sent)
    await asyncio.sleep(0.1)
    assert not vehicle._velocity.active


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_velocity_is_not_revalidated_on_every_setpoint(api, monkeypatch):
    vehicle, vector_cls, sent, checker = _vehicle(api, monkeypatch)
    await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    await asyncio.sleep(0.3)
    await vehicle._stop_velocity()
    assert len(sent) > 3
    assert checker.velocity_checks == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_set_groundspeed_after_takeover_raises(api, monkeypatch):
    vehicle, _, _, checker = _vehicle(api, monkeypatch)
    checker.taken_over = True
    taken_over, _ = _errors(api)
    with pytest.raises(taken_over):
        await vehicle.set_groundspeed(3.0)
