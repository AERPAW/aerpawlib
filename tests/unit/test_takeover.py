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


@pytest.mark.asyncio
async def test_v2_takeover_between_velocity_check_and_first_send_is_not_wrapped(monkeypatch):
    """The checker accepts the velocity, then reports the takeover before the
    first setpoint goes out: set_velocity raises VehicleTakenOverError, not
    VelocityError."""
    vehicle, vector_cls, sent, checker = _vehicle("v2", monkeypatch)

    async def validate_velocity(_current, _velocity):
        checker.taken_over = True
        return True, ""

    checker.validate_velocity = validate_velocity
    taken_over, velocity_error = _errors("v2")
    with pytest.raises(taken_over) as info:
        await vehicle.set_velocity(vector_cls(1.0, 0.0, 0.0))
    assert not isinstance(info.value, velocity_error)
    assert sent == []


# A takeover while a blocking goto/takeoff/land waits (safety pilot mid-goto).


def _fast_takeover_checks(api: str, monkeypatch):
    module = "aerpawlib.v1.vehicle.core_vehicle" if api == "v1" else "aerpawlib.v2.vehicle.base"
    monkeypatch.setattr(f"{module}.TAKEOVER_CHECK_INTERVAL_S", 0.05)


def _waiting_vehicle(api: str, monkeypatch):
    """A drone whose wait loops never finish on their own."""
    from unittest.mock import AsyncMock

    vehicle, _, _, checker = _vehicle(api, monkeypatch)
    _fast_takeover_checks(api, monkeypatch)
    checker.guided_checks = 0
    guided = checker._guided

    def counting_guided():
        checker.guided_checks += 1
        return guided()

    checker._guided = counting_guided
    checker.validate_takeoff_command = lambda *_args: (True, "")
    checker.validate_landing_command = lambda *_args: (True, "")
    system = vehicle._system
    system.action.set_takeoff_altitude = AsyncMock()
    system.action.takeoff = AsyncMock()
    system.action.land = AsyncMock()
    if api == "v1":
        vehicle._lifecycle.has_heartbeat = True
        vehicle._aborted = False
        vehicle._abortable = False
        vehicle._ready_to_move = lambda _: False
        vehicle._mission_start_time = None
        vehicle._ts_state.armed_state.set(True)
    else:
        vehicle._connection.set_link_alive(True)
        vehicle._connection.record_telemetry()
        vehicle._await_preflight_for_takeoff = AsyncMock()
        vehicle.can_takeoff = AsyncMock(return_value=(True, ""))
        vehicle.can_land = AsyncMock(return_value=(True, ""))
        vehicle.done_moving = lambda: False
        vehicle._will_arm = False
        vehicle._test_armed = True
        monkeypatch.setattr(type(vehicle), "armed", property(lambda s: s._test_armed))
    return vehicle, checker


def _disarm(api: str, vehicle) -> None:
    if api == "v1":
        vehicle._ts_state.armed_state.set(False)
    else:
        vehicle._test_armed = False


async def _goto_wait(api: str, vehicle) -> None:
    if api == "v1":
        await vehicle._wait_for_arrival(30, "goto timed out")
    else:
        from aerpawlib.v2.types import Coordinate
        from aerpawlib.v2.vehicle.navigation import wait_for_blocking_goto

        await wait_for_blocking_goto(
            vehicle,
            Coordinate(35.73, -78.69, 30),
            distance_fn=lambda: 50.0,
            tolerance=2.0,
            timeout=30,
            log_prefix="Drone",
        )


def _wait(api: str, which: str, vehicle):
    if which == "goto":
        return _goto_wait(api, vehicle)
    if which == "takeoff":
        return vehicle.takeoff(50) if api == "v1" else vehicle.takeoff(altitude=50)
    return vehicle.land()


WAITS = [(api, which) for api in ("v1", "v2") for which in ("goto", "takeoff", "land")]


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "which"), WAITS)
async def test_takeover_during_a_blocking_wait_raises_promptly(api, which, monkeypatch):
    vehicle, checker = _waiting_vehicle(api, monkeypatch)
    taken_over, _ = _errors(api)
    asyncio.get_running_loop().call_later(0.2, setattr, checker, "taken_over", True)
    start = asyncio.get_running_loop().time()
    with pytest.raises(taken_over):
        await asyncio.wait_for(_wait(api, which, vehicle), timeout=3)
    assert asyncio.get_running_loop().time() - start < 1.5


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_land_without_a_takeover_completes_as_before(api, monkeypatch):
    vehicle, checker = _waiting_vehicle(api, monkeypatch)
    asyncio.get_running_loop().call_later(0.3, _disarm, api, vehicle)
    await asyncio.wait_for(vehicle.land(), timeout=3)
    assert checker.guided_checks >= 2  # asked before LAND and while waiting


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
@pytest.mark.parametrize("which", ["takeoff", "land"])
async def test_a_failing_checker_does_not_fail_a_blocking_wait(api, which, monkeypatch):
    """Only a takeover refusal ends the wait; a checker timeout is ignored.
    takeoff and land turn a TimeoutError into TakeoffError/LandingError, so a
    leaked checker timeout would show."""
    vehicle, checker = _waiting_vehicle(api, monkeypatch)
    if which == "takeoff":
        if api == "v1":
            monkeypatch.setattr("aerpawlib.v1.vehicle.drone.POST_TAKEOFF_STABILIZATION_S", 0)
        else:
            monkeypatch.setattr("aerpawlib.v2.vehicle.drone.POST_TAKEOFF_STABILIZATION_S", 0)

    calls = 0

    def guided():
        nonlocal calls
        calls += 1
        if calls == 1:
            return True, ""  # the check before the command is sent
        raise TimeoutError("SafetyCheckerServer did not respond within 10.0s")

    checker._guided = guided

    def finish():
        if which == "land":
            _disarm(api, vehicle)
        elif api == "v1":
            vehicle._ready_to_move = lambda _: True
            from aerpawlib.v1.util import Coordinate

            monkeypatch.setattr(type(vehicle), "position", property(lambda _self: Coordinate(35.73, -78.695, 50)))
        else:
            vehicle.done_moving = lambda: True

    asyncio.get_running_loop().call_later(0.3, finish)
    await asyncio.wait_for(_wait(api, which, vehicle), timeout=3)
    assert calls >= 2


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_without_a_safety_checker_the_waits_do_not_ask(api, monkeypatch):
    vehicle, checker = _waiting_vehicle(api, monkeypatch)
    vehicle.safety = None
    asyncio.get_running_loop().call_later(0.2, _disarm, api, vehicle)
    await asyncio.wait_for(vehicle.land(), timeout=3)
    assert checker.guided_checks == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
@pytest.mark.parametrize(
    ("refusal", "ends_wait"),
    [
        ("Server error: boom", False),
        ("Unimplemented or missing function request <validate_guided_command_req>", False),
        (f"{TAKEN_OVER_MESSAGE} mode LOITER", True),
    ],
)
async def test_only_a_takeover_refusal_ends_a_goto_wait(api, refusal, ends_wait, monkeypatch):
    vehicle, checker = _waiting_vehicle(api, monkeypatch)
    checker._guided = lambda: (False, refusal)
    running = True

    async def telemetry():
        # Fresh position samples, as the arrival check needs.
        while running:
            if api == "v2":
                vehicle._state._position_seq += 1
                vehicle._connection.record_telemetry()
            await asyncio.sleep(0.02)

    def arrive():
        if api == "v1":
            vehicle._ready_to_move = lambda _: True
        else:
            vehicle.done_moving = lambda: True

    feed = asyncio.create_task(telemetry())
    asyncio.get_running_loop().call_later(0.3, arrive)
    try:
        if ends_wait:
            taken_over, _ = _errors(api)
            with pytest.raises(taken_over):
                await asyncio.wait_for(_goto_wait(api, vehicle), timeout=3)
        else:
            await asyncio.wait_for(_goto_wait(api, vehicle), timeout=3)
    finally:
        running = False
        await feed
