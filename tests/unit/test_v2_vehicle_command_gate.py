"""Regression tests for v2 vehicle command completion, cancel, and shutdown.

Each test drives a real v2 Drone/Rover against a recording fake MAVSDK
``System`` (no network, no SITL). Timeouts are patched short and every wait
is bounded by ``asyncio.wait_for`` so nothing can hang.
"""

from __future__ import annotations

import asyncio
import math
import time
from types import SimpleNamespace

import pytest
from mavsdk.action import ActionError

import aerpawlib.v2.vehicle.base as base_mod
import aerpawlib.v2.vehicle.drone as drone_mod
from aerpawlib.v2.exceptions import LandingError, NavigationError, NotArmableError, TakeoffError
from aerpawlib.v2.types import Coordinate, VectorNED
from aerpawlib.v2.vehicle.drone import Drone
from aerpawlib.v2.vehicle.rover import Rover

LAT, LON = 35.727436, -78.696587
HOME_AMSL = 100.0
BOUND = 2.0  # seconds; upper bound on any single awaited call


class _Action:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.goto_impl = None
        self.land_impl = None

    async def goto_location(self, lat, lon, alt, heading):
        self.calls.append(("goto_location", lat, lon, alt, heading))
        if self.goto_impl is not None:
            await self.goto_impl(lat, lon, alt, heading)

    async def takeoff(self):
        self.calls.append(("takeoff",))

    async def set_takeoff_altitude(self, alt):
        self.calls.append(("set_takeoff_altitude", alt))

    async def land(self):
        self.calls.append(("land",))
        if self.land_impl is not None:
            self.land_impl()

    async def hold(self):
        self.calls.append(("hold",))

    async def arm(self):
        self.calls.append(("arm",))


class _Offboard:
    def __init__(self, log: list) -> None:
        self.log = log

    async def set_velocity_ned(self, v):
        self.log.append(("set_velocity_ned", v.north_m_s, v.east_m_s, v.down_m_s))

    async def start(self):
        self.log.append(("start",))

    async def stop(self):
        self.log.append(("stop",))


class _Direct:
    def __init__(self, log: list) -> None:
        self.log = log
        self.on_send = None

    async def send_message(self, msg):
        self.log.append(("mavlink", msg))
        if self.on_send is not None:
            self.on_send(msg)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(drone_mod, "DEFAULT_GOTO_TIMEOUT_S", 0.2)
    monkeypatch.setattr(drone_mod, "POST_TAKEOFF_STABILIZATION_S", 0.0)
    monkeypatch.setattr(base_mod, "ARMING_SEQUENCE_DELAY_S", 0.0)
    monkeypatch.setattr("aerpawlib._internal.mavlink_ids.resolve_mav_sysid", lambda _s: 1)
    monkeypatch.setattr(
        "aerpawlib._internal.mavlink_ids.make_set_mode_message",
        lambda _sysid, mode: ("set_mode", mode),
    )
    monkeypatch.setattr(
        "aerpawlib._internal.mavlink_ids.make_condition_yaw_message",
        lambda _sysid, heading: ("yaw", heading),
    )


def _make(cls, *, aerpaw: bool = False):
    log: list = []
    action = _Action()
    system = SimpleNamespace(action=action, offboard=_Offboard(log), mavlink_direct=_Direct(log))
    platform = SimpleNamespace(is_connected=True) if aerpaw else None
    v = cls(system, "udpin://127.0.0.1:14550", aerpaw_platform=platform)
    v._aerpaw_forwarder_reachable_cache = False
    v._state.update_armable(True, True, True, True)
    v._state.update_gps(3, 14)
    v._state.update_battery(16.8, 1.0, 90)
    v._state.update_armed(True)
    v._state.update_mode("GUIDED")
    v._state.update_position(LAT, LON, 25.0, HOME_AMSL + 25.0)
    v._state.update_home(LAT, LON, 0.0, HOME_AMSL)
    v._state._last_arm_time = time.monotonic() - 30
    v._connection.set_link_alive(True)
    v._connection.record_telemetry()
    # Landing completes (disarms) as soon as the land command is sent.
    action.land_impl = lambda: v._state.update_armed(False)
    return v, action, log


def _gotos(action: _Action) -> list[tuple]:
    return [c for c in action.calls if c[0] == "goto_location"]


async def _feed(vehicle, lat=LAT, lon=LON, alt=25.0, period=0.02):
    """Keep fresh position samples arriving (like the telemetry stream)."""
    while True:
        vehicle._state.update_position(lat, lon, alt, HOME_AMSL + alt)
        vehicle._connection.record_telemetry()
        await asyncio.sleep(period)


class _Feeder:
    def __init__(self, vehicle, **kw) -> None:
        self.vehicle, self.kw, self.task = vehicle, kw, None

    async def __aenter__(self):
        self.task = asyncio.create_task(_feed(self.vehicle, **self.kw))
        return self

    async def __aexit__(self, *exc):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


def _action_error() -> ActionError:
    return ActionError(SimpleNamespace(result="DENIED", result_str="denied"), "goto_location")


# --- #1 stale ready predicate -------------------------------------------------


@pytest.mark.asyncio
async def test_set_heading_timeout_raises_and_land_still_transmits():
    drone, action, _ = _make(Drone)
    drone._current_heading = 45.0
    with pytest.raises(NavigationError, match="set_heading"):
        await asyncio.wait_for(drone.set_heading(90), BOUND)
    assert drone.done_moving() is True
    assert drone._current_heading == 45.0  # previous lock kept
    await asyncio.wait_for(drone.land(), BOUND)
    assert ("land",) in action.calls


@pytest.mark.asyncio
async def test_blocking_goto_timeout_raises_navigation_error_and_frees_gate():
    drone, action, _ = _make(Drone)
    target = Coordinate(LAT + 0.001, LON, 25.0)
    async with _Feeder(drone):
        with pytest.raises(NavigationError, match="timed out"):
            await asyncio.wait_for(drone.goto_coordinates(target, timeout=0.15), BOUND)
    assert drone.done_moving() is True
    assert len(_gotos(action)) == 1


@pytest.mark.asyncio
async def test_goto_non_action_error_frees_gate():
    drone, action, _ = _make(Drone)

    async def boom(*_a):
        raise ConnectionError("link reset")

    action.goto_impl = boom
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT + 0.001, LON, 25.0)), BOUND)
    assert drone.done_moving() is True


@pytest.mark.asyncio
async def test_takeoff_timeout_frees_gate_so_land_transmits():
    drone, action, _ = _make(Drone)
    drone._state.update_position(LAT, LON, 0.3, HOME_AMSL)
    with pytest.raises(TakeoffError, match="timed out"):
        await asyncio.wait_for(drone.takeoff(25.0), BOUND)
    assert drone.done_moving() is True
    await asyncio.wait_for(drone.land(), BOUND)
    assert ("land",) in action.calls


@pytest.mark.asyncio
async def test_rover_action_error_frees_gate():
    rover, action, _ = _make(Rover)

    async def deny(*_a):
        raise _action_error()

    action.goto_impl = deny
    with pytest.raises(NavigationError):
        await asyncio.wait_for(rover.goto_coordinates(Coordinate(LAT + 0.001, LON, 0)), BOUND)
    assert rover.done_moving() is True


@pytest.mark.asyncio
async def test_land_does_not_wait_for_inflight_goto():
    drone, action, _ = _make(Drone)
    handle = await asyncio.wait_for(
        drone.goto_coordinates(Coordinate(LAT + 0.01, LON, 25.0), blocking=False, timeout=5.0),
        BOUND,
    )
    assert drone.done_moving() is False
    await asyncio.wait_for(drone.land(), 0.5)
    assert action.calls[-1] == ("land",)
    handle.cancel()
    for t in drone._command_tasks:
        t.cancel()


# --- #2 / #10 cancel of non-blocking goto --------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("aerpaw", [True, False])
async def test_drone_cancel_repositions_to_current_fix_without_hold(aerpaw):
    drone, action, _ = _make(Drone, aerpaw=aerpaw)
    drone._state.update_attitude(0.0, 0.0, math.radians(30.0))
    async with _Feeder(drone):
        handle = await asyncio.wait_for(
            drone.goto_coordinates(Coordinate(LAT + 0.01, LON, 25.0), blocking=False, timeout=5.0),
            BOUND,
        )
        await asyncio.wait_for(handle.cancel_async(), 0.5)
    gotos = _gotos(action)
    assert len(gotos) == 2
    _, lat, lon, alt, hdg = gotos[1]
    assert (lat, lon) == (LAT, LON)
    assert alt == pytest.approx(HOME_AMSL + 25.0)
    assert hdg == pytest.approx(30.0)
    assert ("hold",) not in action.calls
    assert drone.done_moving() is True


@pytest.mark.asyncio
async def test_rover_cancel_on_aerpaw_repositions_to_current_fix():
    rover, action, _ = _make(Rover, aerpaw=True)
    async with _Feeder(rover, alt=0.0):
        handle = await asyncio.wait_for(
            rover.goto_coordinates(Coordinate(LAT + 0.01, LON, 0), blocking=False, timeout=5.0),
            BOUND,
        )
        await asyncio.wait_for(handle.cancel_async(), 0.5)
    gotos = _gotos(action)
    assert len(gotos) == 2
    assert gotos[1][1:4] == (LAT, LON, HOME_AMSL)
    assert ("hold",) not in action.calls
    assert rover.done_moving() is True


@pytest.mark.asyncio
async def test_rover_cancel_off_aerpaw_still_holds():
    rover, action, _ = _make(Rover)
    async with _Feeder(rover, alt=0.0):
        handle = await asyncio.wait_for(
            rover.goto_coordinates(Coordinate(LAT + 0.01, LON, 0), blocking=False, timeout=5.0),
            BOUND,
        )
        await asyncio.wait_for(handle.cancel_async(), 0.5)
    assert ("hold",) in action.calls


# --- #3 shutdown with active velocity -------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_aclose_zeroes_velocity_and_stops_offboard_before_closing(cls):
    v, _, log = _make(cls)
    await asyncio.wait_for(v.set_velocity(VectorNED(4, 0, 0)), BOUND)
    log.clear()
    await asyncio.wait_for(v.aclose(), BOUND)
    assert log[:2] == [("set_velocity_ned", 0, 0, 0), ("stop",)], log
    assert v.closed


@pytest.mark.asyncio
async def test_sync_close_schedules_offboard_stop():
    drone, _, log = _make(Drone)
    await asyncio.wait_for(drone.set_velocity(VectorNED(4, 0, 0)), BOUND)
    log.clear()
    with pytest.warns(DeprecationWarning):
        drone.close()
    await asyncio.wait_for(drone._close_task, BOUND)
    assert ("set_velocity_ned", 0, 0, 0) in log and ("stop",) in log


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_cancelled_velocity_loop_zeroes_first(cls):
    v, _, log = _make(cls)
    await asyncio.wait_for(v.set_velocity(VectorNED(4, 0, 0)), BOUND)
    await asyncio.sleep(0.05)  # let the loop start
    log.clear()
    task = v._command_tasks[-1]
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert log[:2] == [("set_velocity_ned", 0, 0, 0), ("stop",)], log


@pytest.mark.asyncio
async def test_aclose_without_offboard_sends_no_offboard_stop():
    """offboard.stop() is LOITER/HOLD on ArduPilot: never send it when idle."""
    drone, _, log = _make(Drone, aerpaw=True)
    await asyncio.wait_for(drone.aclose(), BOUND)
    assert log == []


# --- #5 takeoff altitude ---------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("alt", [0, -5, float("nan"), float("inf")])
async def test_takeoff_rejects_bad_altitude_before_mavlink(alt):
    drone, action, log = _make(Drone)
    drone._state.update_position(LAT, LON, 0.0, HOME_AMSL)
    with pytest.raises(TakeoffError, match="finite value > 0"):
        await asyncio.wait_for(drone.takeoff(alt), BOUND)
    assert action.calls == [] and log == []
    ok, _ = await drone.can_takeoff(alt)
    assert ok is False


@pytest.mark.asyncio
async def test_takeoff_ignores_non_finite_altitude_sample():
    drone, action, _ = _make(Drone)
    drone._state.update_position(LAT, LON, float("inf"), HOME_AMSL)
    with pytest.raises(TakeoffError, match="timed out"):
        await asyncio.wait_for(drone.takeoff(25.0), BOUND)
    assert ("takeoff",) in action.calls


# --- #6 land is busy --------------------------------------------------------------


@pytest.mark.asyncio
async def test_land_marks_vehicle_busy_until_disarm(monkeypatch):
    monkeypatch.setattr(drone_mod, "DEFAULT_GOTO_TIMEOUT_S", 5.0)
    drone, action, _ = _make(Drone)
    action.land_impl = None  # stays airborne until we disarm below
    land_task = asyncio.create_task(drone.land())
    await asyncio.sleep(0.1)
    assert ("land",) in action.calls
    assert drone.done_moving() is False
    goto_task = asyncio.create_task(drone.goto_coordinates(Coordinate(LAT + 0.001, LON, 25.0)))
    await asyncio.sleep(0.15)
    assert _gotos(action) == []
    drone._state.update_armed(False)
    await asyncio.wait_for(land_task, BOUND)
    assert drone.done_moving() is True
    goto_task.cancel()
    await asyncio.gather(goto_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_land_failure_frees_gate(monkeypatch):
    drone, action, _ = _make(Drone)

    async def deny():
        raise ActionError(SimpleNamespace(result="DENIED", result_str="denied"), "land")

    monkeypatch.setattr(action, "land", deny)
    with pytest.raises(LandingError):
        await asyncio.wait_for(drone.land(), BOUND)
    assert drone.done_moving() is True


# --- #7 LAND is not GUIDED --------------------------------------------------------


@pytest.mark.asyncio
async def test_goto_from_land_mode_switches_to_guided_first():
    drone, action, log = _make(Drone, aerpaw=True)
    drone._state.update_mode("LAND")
    assert drone._already_in_guided_mode() is False
    drone._system.mavlink_direct.on_send = lambda _m: drone._state.update_mode("GUIDED")
    seen: list = []

    async def record(*_a):
        seen.append(list(log))

    action.goto_impl = record
    task = asyncio.create_task(drone.goto_coordinates(Coordinate(LAT + 0.001, LON, 25.0)))
    await asyncio.sleep(0.2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert seen and ("mavlink", ("set_mode", drone_mod.COPTER_GUIDED_MODE)) in seen[0]
    assert ("hold",) not in action.calls


# --- #8 position fix / home AMSL / finite target ----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_refused_without_position_fix(cls):
    v, action, _ = _make(cls)
    v._state._position_fix = False
    v._state.update_position(0.0, 0.0, 0.0, 0.0)  # default/no-fix sample
    with pytest.raises(NavigationError, match="position fix"):
        await asyncio.wait_for(v.goto_north(100), BOUND)
    assert _gotos(action) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_refused_until_home_received(cls):
    v, action, _ = _make(cls)
    v._state._home = None
    with pytest.raises(NavigationError, match="home AMSL"):
        await asyncio.wait_for(v.goto_coordinates(Coordinate(LAT + 0.001, LON, 25.0)), BOUND)
    assert _gotos(action) == []
    assert v.done_moving() is True


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_allowed_with_received_zero_home_amsl(cls):
    """AERPAW SITL starts with --home lat,lon,0, so AMSL 0 is a real home."""
    v, action, _ = _make(cls)
    v._state.update_home(LAT, LON, 0.0, 0.0)
    task = asyncio.ensure_future(v.goto_coordinates(Coordinate(LAT + 0.001, LON, 25.0)))
    await asyncio.sleep(0.1)
    task.cancel()
    assert _gotos(action), "goto must be sent with a received AMSL-0 home"


@pytest.mark.asyncio
async def test_goto_rejects_non_finite_target():
    drone, action, _ = _make(Drone)
    with pytest.raises(NavigationError, match="not finite"):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(float("nan"), float("nan"), 25.0)), BOUND)
    assert _gotos(action) == []


# --- #9 movement stops active offboard --------------------------------------------


@pytest.mark.asyncio
async def test_takeoff_stops_active_offboard_first():
    drone, action, log = _make(Drone)
    await asyncio.wait_for(drone.set_velocity(VectorNED(3, 0, 0)), BOUND)
    order: list = []
    orig = action.set_takeoff_altitude

    async def mark(alt):
        order.extend(log)
        await orig(alt)

    action.set_takeoff_altitude = mark
    drone._state.update_position(LAT, LON, 30.0, HOME_AMSL + 30)
    await asyncio.wait_for(drone.takeoff(25.0), BOUND)
    assert ("stop",) in order
    for t in drone._command_tasks:
        t.cancel()


@pytest.mark.asyncio
async def test_land_stops_active_offboard_first():
    drone, _action, log = _make(Drone)
    await asyncio.wait_for(drone.set_velocity(VectorNED(3, 0, 0)), BOUND)
    await asyncio.wait_for(drone.land(), BOUND)
    assert ("stop",) in log
    assert drone._offboard.active is False


@pytest.mark.asyncio
async def test_rover_goto_stops_active_offboard_first():
    rover, action, log = _make(Rover)
    await asyncio.wait_for(rover.set_velocity(VectorNED(3, 0, 0)), BOUND)
    task = asyncio.create_task(rover.goto_coordinates(Coordinate(LAT + 0.001, LON, 0)))
    await asyncio.sleep(0.1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert ("stop",) in log and _gotos(action)


# --- #11 EKF wait is bounded ------------------------------------------------------


@pytest.mark.asyncio
async def test_standalone_arm_ekf_wait_times_out(monkeypatch):
    monkeypatch.setattr(base_mod, "ARMABLE_TIMEOUT_S", 0.1)
    drone, action, _ = _make(Drone)
    drone._state.update_armed(False)
    drone._state.update_ekf_from_flags(127)  # estimates ok, predict bits missing
    with pytest.raises(NotArmableError, match="EKF"):
        await asyncio.wait_for(drone._auto_arm_standalone(), BOUND)
    assert ("arm",) not in action.calls


# --- #12 arrival needs a live link and fresh, repeated samples --------------------


@pytest.mark.asyncio
async def test_arrival_fails_when_link_down():
    drone, _action, _ = _make(Drone)
    drone._connection.set_link_alive(False)
    with pytest.raises(NavigationError, match="link is down"):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 25.0), timeout=1.0), BOUND)
    assert drone.done_moving() is True


@pytest.mark.asyncio
async def test_arrival_fails_on_stale_telemetry():
    drone, _, _ = _make(Drone)
    drone._connection.last_telemetry_at = time.monotonic() - 30.0
    with pytest.raises(NavigationError, match="stale"):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 25.0), timeout=1.0), BOUND)


@pytest.mark.asyncio
async def test_single_in_tolerance_sample_is_not_arrival():
    drone, _, _ = _make(Drone)
    # Already inside the bubble, but no further samples arrive.
    with pytest.raises(NavigationError, match="timed out"):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 25.0), timeout=0.2), BOUND)
    async with _Feeder(drone):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 25.0), timeout=1.0), BOUND)


# --- coincident goto yaw (v1 #15 applied to v2) -----------------------------------


@pytest.mark.asyncio
async def test_vertical_goto_keeps_current_heading():
    drone, action, _ = _make(Drone)
    drone._state.update_attitude(0.0, 0.0, math.radians(123.0))
    task = asyncio.create_task(drone.goto_coordinates(Coordinate(LAT, LON, 40.0)))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert _gotos(action)[0][4] == pytest.approx(123.0)


# --- #16 battery ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_nan_battery_sample_does_not_kill_subscription():
    async def empty(*_a, **_k):
        return
        yield

    async def battery():
        yield SimpleNamespace(voltage_v=16.0, current_battery_a=1.0, remaining_percent=float("nan"))
        yield SimpleNamespace(voltage_v=15.9, current_battery_a=1.0, remaining_percent=77.0)

    class _Telemetry:
        def __getattr__(self, _name):
            return empty

    telemetry = _Telemetry()
    telemetry.battery = battery
    system = SimpleNamespace(
        telemetry=telemetry,
        mavlink_direct=SimpleNamespace(message=empty),
        core=SimpleNamespace(connection_state=empty),
    )
    drone = Drone(system, "udpin://127.0.0.1:14550")
    await drone._start_telemetry()
    await asyncio.wait_for(asyncio.gather(*drone._telemetry_tasks), BOUND)
    assert all(t.exception() is None for t in drone._telemetry_tasks)
    assert drone.battery.level == 77
