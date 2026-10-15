"""Regression tests for the v1 compat vehicle layer (command gate, guards).

The real v1 ``Drone``/``Rover`` constructors run with ``_connect_sync``
patched out, against a recording fake MAVSDK ``System``. MAVSDK calls run on
the test loop. Timeouts are patched short and waits are bounded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest
from mavsdk.action import ActionError

import aerpawlib.v1.vehicle.core_vehicle as core_mod
import aerpawlib.v1.vehicle.drone as drone_mod
from aerpawlib.v1.constants import GUIDED_MODE_NAME
from aerpawlib.v1.exceptions import (
    ConnectionTimeoutError,
    HeadingError,
    NavigationError,
    NotArmableError,
    RTLError,
    TakeoffError,
)
from aerpawlib.v1.util import Coordinate
from aerpawlib.v1.vehicle import telemetry_subscriptions as telem_mod
from aerpawlib.v1.vehicle.connection_lifecycle import ConnectionLifecycle
from aerpawlib.v1.vehicle.core_vehicle import Vehicle
from aerpawlib.v1.vehicle.drone import Drone
from aerpawlib.v1.vehicle.rover import Rover
from aerpawlib.v1.vehicle.state import InitPhase
from aerpawlib.v1.vehicle.telemetry_compat import _GPSInfoCompat

LAT, LON = 35.727436, -78.696587
HOME_AMSL = 100.0
BOUND = 2.0


class _Action:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.goto_impl = None
        self.vehicle = None

    async def goto_location(self, lat, lon, alt, heading):
        self.calls.append(("goto_location", lat, lon, alt, heading))
        if self.goto_impl is not None:
            await self.goto_impl()

    async def set_takeoff_altitude(self, alt):
        self.calls.append(("set_takeoff_altitude", alt))

    async def takeoff(self):
        self.calls.append(("takeoff",))

    async def land(self):
        self.calls.append(("land",))

    async def arm(self):
        self.calls.append(("arm",))


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    def _fake_connect(self):
        self._lifecycle.has_heartbeat = True
        self._ts_state.armed_telemetry_received.set(True)

    monkeypatch.setattr(Vehicle, "_connect_sync", _fake_connect)
    monkeypatch.setattr(Vehicle, "_in_aerpaw", lambda _self: False)
    monkeypatch.setattr(drone_mod, "DEFAULT_GOTO_TIMEOUT_S", 0.2)
    monkeypatch.setattr(drone_mod, "POST_TAKEOFF_STABILIZATION_S", 0.0)
    monkeypatch.setattr(core_mod, "ARMING_SEQUENCE_DELAY_S", 0.0)
    monkeypatch.setattr(core_mod, "DEFAULT_GOTO_TIMEOUT_S", 1.0)
    monkeypatch.setattr("aerpawlib._internal.mavlink_ids.resolve_mav_sysid", lambda _s: 1)
    monkeypatch.setattr(
        "aerpawlib._internal.mavlink_ids.make_condition_yaw_message",
        lambda _sysid, heading: ("yaw", heading),
    )
    monkeypatch.setattr(
        "aerpawlib._internal.mavlink_ids.make_set_mode_message",
        lambda _sysid, mode: ("set_mode", mode),
    )


def _make(cls):
    v = cls("udpin://127.0.0.1:14550")
    action = _Action()
    sent: list = []

    async def send_message(msg):
        sent.append(msg)

    v._system = SimpleNamespace(action=action, mavlink_direct=SimpleNamespace(send_message=send_message))

    async def _direct(coro):
        return await coro

    v._run_on_mavsdk_loop = _direct
    st = v._ts_state
    st.armed_state.set(True)
    st.is_armable_state.set(True)
    st.mode.set("GUIDED")
    st.position_lat.set(LAT)
    st.position_lon.set(LON)
    st.position_alt.set(25.0)
    st.home_position.set(Coordinate(LAT, LON, 0))
    st.home_abs_alt.set(HOME_AMSL)
    st.last_arm_time.set(time.time() - 30)
    return v, action, sent


def _gotos(action):
    return [c for c in action.calls if c[0] == "goto_location"]


# --- #1 home AMSL / position fix guard -------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_allowed_with_received_zero_home_amsl(cls):
    """AERPAW SITL starts with --home lat,lon,0, so AMSL 0 is a real home."""
    v, action, _ = _make(cls)
    v._ts_state.home_abs_alt.set(0.0)
    task = asyncio.ensure_future(v.goto_coordinates(Coordinate(LAT + 0.001, LON, 30)))
    await asyncio.sleep(0.1)
    task.cancel()
    assert _gotos(action), "goto must be sent with a received AMSL-0 home"


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_refused_with_missing_home_or_zero_home(cls):
    v, action, _ = _make(cls)
    v._ts_state.home_position.set(Coordinate(0.0, 0.0, 0.0))
    with pytest.raises(NavigationError, match="home AMSL"):
        await asyncio.wait_for(v.goto_coordinates(Coordinate(LAT + 0.001, LON, 30)), BOUND)
    v._ts_state.home_position.set(None)
    with pytest.raises(NavigationError, match="home AMSL"):
        await asyncio.wait_for(v.goto_coordinates(Coordinate(LAT + 0.001, LON, 30)), BOUND)
    assert _gotos(action) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_refused_without_position_fix(cls):
    v, action, _ = _make(cls)
    v._ts_state.position_lat.set(0.0)
    v._ts_state.position_lon.set(0.0)
    with pytest.raises(NavigationError, match="position fix"):
        await asyncio.wait_for(v.goto_coordinates(Coordinate(LAT, LON, 30)), BOUND)
    assert _gotos(action) == []


@pytest.mark.asyncio
async def test_goto_sends_relative_alt_plus_home_amsl():
    drone, action, _ = _make(Drone)
    target = Coordinate(LAT + 0.001, LON, 30)
    drone._ts_state.position_lat.set(target.lat)  # already there -> completes
    drone._ts_state.position_alt.set(30.0)
    await asyncio.wait_for(drone.goto_coordinates(target), BOUND)
    assert _gotos(action)[0][3] == pytest.approx(HOME_AMSL + 30)


# --- #3 set_heading -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_heading_timeout_raises_and_restores_gate():
    drone, _action, _ = _make(Drone)
    drone._current_heading = 45.0
    with pytest.raises(HeadingError, match="timed out"):
        await asyncio.wait_for(drone.set_heading(270), BOUND)
    assert drone.done_moving() is True
    assert drone._current_heading == 45.0


@pytest.mark.asyncio
async def test_set_heading_send_failure_raises():
    drone, _, _ = _make(Drone)

    async def fail(_msg):
        raise RuntimeError("yaw rejected")

    drone._system.mavlink_direct.send_message = fail
    with pytest.raises(HeadingError, match="yaw rejected"):
        await asyncio.wait_for(drone.set_heading(45), BOUND)
    assert drone.done_moving() is True
    assert drone._current_heading is None


@pytest.mark.asyncio
async def test_set_heading_rejects_non_finite():
    drone, _, sent = _make(Drone)
    with pytest.raises(HeadingError):
        await drone.set_heading(float("inf"))
    assert sent == []


# --- #12 goto timeout resets the gate ------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_timeout_resets_ready_gate(cls):
    v, _action, _ = _make(cls)
    with pytest.raises(NavigationError):
        await asyncio.wait_for(v.goto_coordinates(Coordinate(LAT + 0.01, LON, 25), timeout=0.15), BOUND)
    assert v.done_moving() is True


@pytest.mark.asyncio
async def test_rover_action_error_resets_ready_gate():
    rover, action, _ = _make(Rover)

    async def deny():
        raise ActionError(SimpleNamespace(result="DENIED", result_str="denied"), "goto_location")

    action.goto_impl = deny
    with pytest.raises(NavigationError):
        await asyncio.wait_for(rover.goto_coordinates(Coordinate(LAT + 0.01, LON, 0)), BOUND)
    assert rover.done_moving() is True


# --- #14 takeoff(wait_for_throttle=...) ------------------------------------------------


@pytest.mark.asyncio
async def test_takeoff_accepts_wait_for_throttle_and_warns(caplog):
    drone, action, _ = _make(Drone)
    drone._ts_state.position_alt.set(30.0)
    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(drone.takeoff(25, wait_for_throttle=True), BOUND)
    assert ("takeoff",) in action.calls
    assert "wait_for_throttle" in caplog.text


# --- #5 (v1) takeoff altitude ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("alt", [0, -5, float("nan"), float("inf")])
async def test_takeoff_rejects_bad_altitude_before_mavlink(alt):
    drone, action, _ = _make(Drone)
    with pytest.raises(TakeoffError, match="finite value > 0"):
        await asyncio.wait_for(drone.takeoff(alt), BOUND)
    assert action.calls == []


@pytest.mark.asyncio
async def test_takeoff_timeout_resets_gate_and_ignores_inf_alt():
    drone, action, _ = _make(Drone)
    drone._ts_state.position_alt.set(float("inf"))
    with pytest.raises(TakeoffError, match="timed out"):
        await asyncio.wait_for(drone.takeoff(25), BOUND)
    assert ("takeoff",) in action.calls
    assert drone.done_moving() is True


# --- #15 coincident points keep current heading -----------------------------------------


@pytest.mark.asyncio
async def test_vertical_goto_keeps_current_heading():
    drone, action, _ = _make(Drone)
    drone._ts_state.heading_deg.set(123.0)
    drone._ts_state.position_alt.set(40.0)  # arrive at once
    await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 40)), BOUND)
    assert _gotos(action)[0][4] == pytest.approx(123.0)


@pytest.mark.asyncio
async def test_explicit_target_heading_still_wins_for_vertical_goto():
    drone, action, _ = _make(Drone)
    drone._ts_state.heading_deg.set(123.0)
    drone._ts_state.position_alt.set(40.0)
    await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 40), target_heading=10), BOUND)
    assert _gotos(action)[0][4] == pytest.approx(10.0)


# --- v2 #6 / #7 / #9 applied to v1 ------------------------------------------------------


def test_land_mode_is_not_already_guided():
    drone, _, _ = _make(Drone)
    drone._ts_state.mode.set("LAND")
    assert drone._already_in_guided_mode() is False
    drone._ts_state.mode.set("GUIDED")
    assert drone._already_in_guided_mode() is True


@pytest.mark.asyncio
async def test_land_preempts_stale_gate_and_stays_busy(monkeypatch):
    monkeypatch.setattr(drone_mod, "DEFAULT_GOTO_TIMEOUT_S", 5.0)
    drone, action, _ = _make(Drone)
    drone._ready_to_move = lambda _: False  # e.g. an unfinished waypoint
    task = asyncio.create_task(drone.land())
    await asyncio.sleep(0.1)
    assert ("land",) in action.calls
    assert drone.done_moving() is False
    drone._ts_state.armed_state.set(False)
    await asyncio.wait_for(task, BOUND)
    assert drone.done_moving() is True


@pytest.mark.asyncio
async def test_takeoff_stops_active_offboard_first():
    drone, _action, _ = _make(Drone)
    log: list = []

    async def set_velocity_ned(v):
        log.append(("set", v.north_m_s))

    async def stop():
        log.append(("stop",))

    drone._system.offboard = SimpleNamespace(set_velocity_ned=set_velocity_ned, stop=stop)
    drone._offboard_active = True
    drone._ts_state.position_alt.set(30.0)
    await asyncio.wait_for(drone.takeoff(25), BOUND)
    assert ("stop",) in log
    assert drone._offboard_active is False


# --- v2 #11 applied to v1: EKF wait is bounded ---------------------------------------------


@pytest.mark.asyncio
async def test_standalone_arm_ekf_wait_times_out(monkeypatch):
    monkeypatch.setattr(core_mod, "ARMABLE_TIMEOUT_S", 0.1)
    monkeypatch.setattr(core_mod, "AERPAW_Platform", SimpleNamespace(_connected=False))
    drone, action, _ = _make(Drone)
    drone._ts_state.armed_state.set(False)
    gps = _GPSInfoCompat()
    gps.fix_type = 3
    drone._ts_state.gps_val.set(gps)
    drone._ts_state.ekf_ready.set(False)
    with pytest.raises(NotArmableError, match="EKF"):
        await asyncio.wait_for(drone._arm_vehicle(), BOUND)
    assert ("arm",) not in action.calls


# --- v2 #16 applied to v1: NaN battery sample ----------------------------------------------


@pytest.mark.asyncio
async def test_nan_battery_sample_is_skipped():
    from aerpawlib.v1.vehicle import telemetry_subscriptions

    drone, _, _ = _make(Drone)

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
    drone._system = SimpleNamespace(
        telemetry=telemetry,
        mavlink_direct=SimpleNamespace(message=empty),
        core=SimpleNamespace(connection_state=empty),
    )
    drone._telemetry_tasks = []
    await telemetry_subscriptions.start_telemetry(drone)
    await asyncio.sleep(0.2)  # well before the 1 s retry back-off
    drone._lifecycle.stop()
    for t in drone._telemetry_tasks:
        t.cancel()
    await asyncio.gather(*drone._telemetry_tasks, return_exceptions=True)
    assert drone.battery.level == 77


# --- #13 AERPAW_Platform proxy -------------------------------------------------------------


def test_proxy_setattr_before_first_use_reaches_instance(monkeypatch):
    import aerpawlib.v1.aerpaw as aerpaw_mod

    class _FakeAERPAW:
        def __init__(self) -> None:
            self._no_stdout = False
            self._connected = False

    monkeypatch.setattr(aerpaw_mod, "AERPAW", _FakeAERPAW)
    proxy = aerpaw_mod._AERPAWLazyProxy()
    proxy._no_stdout = True
    assert "_no_stdout" not in proxy.__dict__
    assert proxy._get_instance()._no_stdout is True
    assert proxy._no_stdout is True
    proxy._connected = True
    assert proxy._get_instance()._connected is True


# --- #8 connection strings -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (":14550", "udpin://0.0.0.0:14550"),
        ("14550", "udpin://0.0.0.0:14550"),
        ("udpin:0.0.0.0:14550", "udpin://0.0.0.0:14550"),
        ("udpin:127.0.0.1:14551", "udpin://127.0.0.1:14551"),
        ("tcp:127.0.0.1:5760", "tcp://127.0.0.1:5760"),
        ("udp:127.0.0.1:14550", "udpin://127.0.0.1:14550"),
        ("udpin://:14550", "udpin://:14550"),
        ("tcp://127.0.0.1:5760", "tcp://127.0.0.1:5760"),
        ("serial:///dev/ttyUSB0:57600", "serial:///dev/ttyUSB0:57600"),
    ],
)
def test_dronekit_connection_strings_are_normalized(given, expected):
    from aerpawlib._internal.connection_string import (
        normalize_mavsdk_connection_string,
        parse_udp_connection_port,
    )

    assert normalize_mavsdk_connection_string(given) == expected
    if expected.startswith("udpin://0.0.0.0:"):
        assert parse_udp_connection_port(expected) == ("0.0.0.0", 14550)


@pytest.mark.asyncio
async def test_rover_goto_stops_active_offboard_first():
    rover, action, _ = _make(Rover)
    log: list = []

    async def set_velocity_ned(v):
        log.append(("set", v.north_m_s))

    async def stop():
        log.append(("stop",))

    rover._system.offboard = SimpleNamespace(set_velocity_ned=set_velocity_ned, stop=stop)
    rover._offboard_active = True
    target = Coordinate(LAT, LON, 0)  # already there -> completes
    await asyncio.wait_for(rover.goto_coordinates(target), BOUND)
    assert log == [("set", 0), ("stop",)]
    assert _gotos(action)


# --- v1_vehicle report additions -------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("tol", [0, -0.5, 1.5, float("nan")])
async def test_takeoff_rejects_bad_min_alt_tolerance(tol):
    drone, action, _ = _make(Drone)
    with pytest.raises(TakeoffError, match="min_alt_tolerance"):
        await asyncio.wait_for(drone.takeoff(20, min_alt_tolerance=tol), BOUND)
    assert action.calls == []


@pytest.mark.asyncio
async def test_rtl_does_not_land_far_from_home_when_goto_fails():
    drone, action, _ = _make(Drone)
    drone._ts_state.position_lat.set(LAT + 0.009)  # ~1 km north of home

    async def failing_goto(*_a, **_k):
        raise NavigationError("timed out")

    drone.goto_coordinates = failing_goto
    with pytest.raises(RTLError, match="not landing"):
        await asyncio.wait_for(drone.return_to_launch(), BOUND)
    assert ("land",) not in action.calls


@pytest.mark.asyncio
async def test_rtl_lands_when_goto_fails_but_already_at_home():
    drone, action, _ = _make(Drone)

    async def failing_goto(*_a, **_k):
        raise NavigationError("timed out")

    async def land_disarms():
        action.calls.append(("land",))
        drone._ts_state.armed_state.set(False)

    drone.goto_coordinates = failing_goto
    action.land = land_disarms
    await asyncio.wait_for(drone.return_to_launch(), BOUND)
    assert ("land",) in action.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [Drone, Rover])
async def test_goto_fails_fast_when_disconnected(cls):
    v, action, _ = _make(cls)

    async def drop_link():
        v._lifecycle.has_heartbeat = False

    action.goto_impl = drop_link
    t0 = time.monotonic()
    with pytest.raises(NavigationError, match="disconnected"):
        await asyncio.wait_for(v.goto_coordinates(Coordinate(LAT, LON, 25), timeout=1.0), BOUND)
    assert time.monotonic() - t0 < 0.5
    assert v._ready_to_move(v) is True


@pytest.mark.asyncio
async def test_goto_arrival_checks_altitude_separately():
    drone, _action, _ = _make(Drone)
    drone._ts_state.position_alt.set(33.0)  # exact lat/lon, 3 m high
    await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 30), tolerance=2, timeout=0.5), BOUND)
    drone, _, _ = _make(Drone)
    drone._ts_state.position_alt.set(40.0)  # 10 m off vertically is not arrival
    with pytest.raises(NavigationError):
        await asyncio.wait_for(drone.goto_coordinates(Coordinate(LAT, LON, 30), tolerance=2, timeout=0.2), BOUND)


@pytest.mark.asyncio
async def test_successful_land_restores_gate_for_next_takeoff():
    drone, action, _ = _make(Drone)

    async def land_disarms():
        action.calls.append(("land",))
        drone._ts_state.armed_state.set(False)

    action.land = land_disarms
    await asyncio.wait_for(drone.land(), BOUND)
    assert drone._ready_to_move(drone) is True


def test_close_stops_mavsdk_server():
    drone, _, _ = _make(Drone)
    stopped = []
    drone._system._stop_mavsdk_server = lambda: stopped.append(True)
    drone.close()
    assert stopped == [True]
    assert drone._system is None


def test_constructor_refusing_armed_vehicle_cleans_up(monkeypatch):
    stopped = []

    def _armed_connect(self):
        self._lifecycle.has_heartbeat = True
        self._ts_state.armed_telemetry_received.set(True)
        self._ts_state.armed_state.set(True)
        self._system = SimpleNamespace(_stop_mavsdk_server=lambda: stopped.append(True))

    monkeypatch.setattr(Vehicle, "_connect_sync", _armed_connect)
    with pytest.raises(NotArmableError, match="already armed"):
        Drone("udpin://192.168.32.25:14550")
    assert stopped == [True]


def test_connect_timeout_stops_thread_and_server(monkeypatch):
    monkeypatch.undo()  # use the real _connect_sync
    monkeypatch.setattr(core_mod, "CONNECTION_TIMEOUT_S", 0.2)
    monkeypatch.setattr(core_mod, "MAVSDK_THREAD_SHUTDOWN_TIMEOUT_S", 2)
    monkeypatch.setattr(core_mod, "is_tcp_port_in_use", lambda *_a: False)
    stopped = []
    created = []

    async def _hang(self):
        self._system = SimpleNamespace(_stop_mavsdk_server=lambda: stopped.append(True))
        await asyncio.sleep(30)

    real_init = Vehicle.__init__

    def _init(self, *a, **k):
        created.append(self)
        real_init(self, *a, **k)

    monkeypatch.setattr(Vehicle, "_connect_async", _hang)
    monkeypatch.setattr(Vehicle, "__init__", _init)
    with pytest.raises(ConnectionTimeoutError):
        Rover("tcp://127.0.0.1:1")
    assert stopped == [True]
    assert not created[0]._mavsdk_thread.is_alive()


@pytest.mark.asyncio
async def test_rover_guided_mode_runs_on_mavsdk_loop():
    rover, _, sent = _make(Rover)
    rover._ts_state.mode.set("MANUAL")
    on_loop = []

    async def _direct(coro):
        on_loop.append(True)
        result = await coro
        rover._ts_state.mode.set(GUIDED_MODE_NAME)
        return result

    rover._run_on_mavsdk_loop = _direct
    await asyncio.wait_for(rover._set_guided_mode(), BOUND)
    assert on_loop == [True] and sent


def test_rover_preflight_cancels_mode_switch_future_on_timeout(monkeypatch):
    import concurrent.futures

    import aerpawlib.v1.vehicle.rover as rover_mod

    rover, _, _ = _make(Rover)
    fut = concurrent.futures.Future()
    fut.result = lambda timeout=None: (_ for _ in ()).throw(concurrent.futures.TimeoutError())

    def _schedule(coro, _loop):
        coro.close()
        return fut

    monkeypatch.setattr(rover_mod.asyncio, "run_coroutine_threadsafe", _schedule)
    monkeypatch.setattr(Vehicle, "_preflight_wait", lambda _self, _arm: None)
    rover._mavsdk_loop = object()
    rover._preflight_wait(True)
    assert fut.cancelled()


@pytest.mark.asyncio
async def test_rover_goto_bumps_velocity_generation():
    rover, _, _ = _make(Rover)
    gen = rover._velocity_generation
    await asyncio.wait_for(rover.goto_coordinates(Coordinate(LAT, LON, 0)), BOUND)
    assert rover._velocity_generation > gen


@pytest.mark.asyncio
async def test_guided_switch_never_holds_on_aerpaw_node(monkeypatch):
    monkeypatch.setenv("AP_EXPENV_EXP_NUM", "1234")
    drone, action, sent = _make(Drone)
    drone._ts_state.mode.set("STABILIZE")
    holds = []

    async def hold():
        holds.append(True)

    action.hold = hold

    async def send(msg):
        sent.append(msg)
        drone._ts_state.mode.set("GUIDED")

    drone._system.mavlink_direct.send_message = send
    assert drone._must_avoid_loiter() is True
    drone._ts_state.mode.set("HOLD")
    assert drone._already_in_guided_mode() is False
    await asyncio.wait_for(drone._set_guided_mode(), BOUND)
    assert holds == []
    assert ("set_mode", drone_mod.COPTER_GUIDED_MODE) in sent


@pytest.mark.asyncio
async def test_arm_waiter_fails_when_leader_fails():
    drone, _, _ = _make(Drone)
    drone._ts_state.armed_state.set(False)
    drone._init_phase = InitPhase.IN_PROGRESS
    task = asyncio.create_task(drone._arm_vehicle())
    await asyncio.sleep(0.1)
    drone._init_phase = InitPhase.PENDING  # leader gave up
    with pytest.raises(NotArmableError):
        await asyncio.wait_for(task, BOUND)


def _telem_vehicle():
    lifecycle = ConnectionLifecycle()
    lifecycle.has_heartbeat = True
    return SimpleNamespace(_lifecycle=lifecycle)


def _empty_stream(*_a, **_k):
    async def gen():
        return
        yield

    return gen()


class _EmptyTelemetry:
    def __getattr__(self, _name):
        return _empty_stream


@pytest.mark.asyncio
async def test_failing_ekf_subscription_does_not_busy_spin(monkeypatch):
    monkeypatch.setattr(telem_mod, "_STREAM_MAX_BACKOFF_S", 0.02)
    drone, _, _ = _make(Drone)
    ekf_calls = []

    def _message(name):
        if name == "EKF_STATUS_REPORT":
            ekf_calls.append(True)
            raise RuntimeError("EKF_STATUS_REPORT unsupported")
        return _empty_stream()

    drone._system = SimpleNamespace(
        telemetry=_EmptyTelemetry(),
        mavlink_direct=SimpleNamespace(message=_message),
        core=SimpleNamespace(connection_state=_empty_stream),
    )
    drone._telemetry_tasks = []
    await telem_mod.start_telemetry(drone)
    await asyncio.sleep(0.3)
    drone._lifecycle.stop()
    for t in drone._telemetry_tasks:
        t.cancel()
    await asyncio.gather(*drone._telemetry_tasks, return_exceptions=True)
    # Backs off, then gives up: not ~10^5 re-subscriptions.
    assert len(ekf_calls) == telem_mod.MAX_TELEMETRY_RETRIES


@pytest.mark.asyncio
async def test_stream_that_ends_is_not_resubscribed_in_a_tight_loop(monkeypatch):
    monkeypatch.setattr(telem_mod, "_STREAM_RESTART_DELAY_S", 0.1)
    vehicle = _telem_vehicle()
    calls = []

    async def ends():
        calls.append(True)

    task = asyncio.create_task(telem_mod.resilient_telemetry_task(vehicle, "gps", ends))
    await asyncio.sleep(0.25)
    vehicle._lifecycle.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert len(calls) <= 4


@pytest.mark.asyncio
async def test_critical_stream_keeps_retrying_and_blocks_connected_until_recovered(monkeypatch):
    monkeypatch.setattr(telem_mod, "_STREAM_MAX_BACKOFF_S", 0.01)
    vehicle = _telem_vehicle()
    vehicle._link_connected = True
    calls = []

    async def fails():
        calls.append(True)
        raise RuntimeError("stream broke")

    task = asyncio.create_task(telem_mod.resilient_telemetry_task(vehicle, "position", fails))
    await asyncio.sleep(0.2)
    assert len(calls) > telem_mod.MAX_TELEMETRY_RETRIES  # did not give up
    assert not task.done()
    assert vehicle._lifecycle.has_heartbeat is False
    assert "position" in vehicle._dead_telemetry_streams
    telem_mod._mark_stream_alive(vehicle, "position")
    assert vehicle._lifecycle.has_heartbeat is True
    vehicle._lifecycle.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_connection_update_does_not_report_connected_with_dead_position_stream():
    drone, _, _ = _make(Drone)
    drone._lifecycle.has_heartbeat = False
    drone._dead_telemetry_streams = {"position"}

    async def states():
        yield SimpleNamespace(is_connected=True)

    drone._system = SimpleNamespace(
        telemetry=_EmptyTelemetry(),
        mavlink_direct=SimpleNamespace(message=_empty_stream),
        core=SimpleNamespace(connection_state=states),
    )
    drone._telemetry_tasks = []
    await telem_mod.start_telemetry(drone)
    await asyncio.sleep(0.1)
    assert drone._lifecycle.has_heartbeat is False
    drone._lifecycle.stop()
    for t in drone._telemetry_tasks:
        t.cancel()
    await asyncio.gather(*drone._telemetry_tasks, return_exceptions=True)
