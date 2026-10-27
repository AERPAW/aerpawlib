"""set_velocity streams GUIDED setpoints for drones and rovers, v1 and v2.

MAVSDK offboard is never used: offboard.stop() switches ArduPilot to
LOITER/HOLD, which the AERPAW C-VM filter treats as fatal. Starting, replacing
and stopping velocity are all SET_POSITION_TARGET_LOCAL_NED setpoints, so the
vehicle never changes mode.
"""

import asyncio
import json
import math
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymavlink import mavutil

from aerpawlib._internal.velocity import VelocityStream
from aerpawlib.v1.util import VectorNED as V1VectorNED
from aerpawlib.v1.vehicle.state import ThreadSafeVehicleState
from aerpawlib.v2.types import VectorNED as V2VectorNED

IGNORE_VELOCITY = 0b111000
IGNORE_YAW = 0b010000000000
# C-VM filter POSITION_TYPEMASK_CHECK: position and acceleration must be ignored.
FILTER_MASK = 0b000111000111
HEADING_DEG = 90.0
# Seen on the autopilot's SYS_STATUS; deliberately not 1.
AUTOPILOT_SYSID = 7
FIRST = (1.0, 2.0, 3.0)
SECOND = (0.0, -2.0, 0.0)
CASES = [(api, kind) for api in ("v1", "v2") for kind in ("drone", "rover")]


def _recording_system() -> tuple[MagicMock, list]:
    sent: list = []
    system = MagicMock()
    # MAVSDK's own GCS id, as on a real System; never the vehicle's.
    system._sysid = 245

    async def send_message(msg):
        sent.append((msg.message_name, json.loads(msg.fields_json)))

    system.mavlink_direct.send_message = AsyncMock(side_effect=send_message)
    return system, sent


def _vehicle(api: str, kind: str, monkeypatch, system):
    if api == "v1":
        from aerpawlib.v1.vehicle.connection_lifecycle import ConnectionLifecycle
        from aerpawlib.v1.vehicle.drone import Drone
        from aerpawlib.v1.vehicle.rover import Rover

        cls = Drone if kind == "drone" else Rover
        vehicle = cls.__new__(cls)
        vehicle._velocity = VelocityStream(0.05)
        vehicle.safety = None
        vehicle._lifecycle = ConnectionLifecycle()
        vehicle._current_heading = None
        vehicle._event_log = None
        vehicle._command_tasks = []
        vehicle._system = system
        vehicle._ts_state = ThreadSafeVehicleState()
        vehicle._ts_state.autopilot_sysid.set(AUTOPILOT_SYSID)

        async def _direct(coro):
            return await coro

        vehicle._run_on_mavsdk_loop = _direct
        vector_cls = V1VectorNED
    else:
        from aerpawlib.v2.vehicle.drone import Drone
        from aerpawlib.v2.vehicle.rover import Rover

        cls = Drone if kind == "drone" else Rover
        vehicle = cls(system, "udpin://127.0.0.1:14550")
        vehicle._state.update_autopilot_sysid(AUTOPILOT_SYSID)
        vector_cls = V2VectorNED

    async def _ready():
        return None

    vehicle.await_ready_to_move = _ready
    monkeypatch.setattr(cls, "heading", property(lambda _self: HEADING_DEG))
    # On the testbed: drone velocity used to raise VelocityError here.
    monkeypatch.setattr(cls, "_must_avoid_loiter", lambda _self: True)
    return vehicle, vector_cls


def _is_stop(kind: str, fields: dict) -> bool:
    if kind == "rover":
        return fields["type_mask"] & IGNORE_VELOCITY == IGNORE_VELOCITY
    return (fields["vx"], fields["vy"], fields["vz"]) == (0.0, 0.0, 0.0)


def _velocity_error(api: str):
    if api == "v1":
        from aerpawlib.v1.exceptions import VelocityError
    else:
        from aerpawlib.v2.exceptions import VelocityError
    return VelocityError


async def _wait_for_stop(kind: str, sent: list) -> None:
    for _ in range(100):
        if any(_is_stop(kind, f) for _, f in sent):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"no stop setpoint sent: {sent}")


def _cancel(vehicle) -> None:
    for task in vehicle._command_tasks:
        task.cancel()


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_velocity_streams_then_stops_in_guided(api, kind, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST), duration=0.2)
    await asyncio.sleep(0.5)

    names = {name for name, _ in sent}
    # No COMMAND_LONG: no DO_SET_MODE, so the vehicle never leaves GUIDED.
    assert names == {"SET_POSITION_TARGET_LOCAL_NED"}, sent
    assert system.offboard.method_calls == []
    for _, fields in sent:
        assert fields["type_mask"] & FILTER_MASK == FILTER_MASK, fields
        assert fields["coordinate_frame"] == mavutil.mavlink.MAV_FRAME_LOCAL_NED

    velocity = [f for _, f in sent if not _is_stop(kind, f)]
    assert len(velocity) > 1, "setpoint must be resent so ArduPilot does not time out"
    down = FIRST[2] if kind == "drone" else 0.0
    assert all((f["vx"], f["vy"], f["vz"]) == (FIRST[0], FIRST[1], down) for f in velocity)

    stops = [f for _, f in sent if _is_stop(kind, f)]
    assert len(stops) == 1, sent
    assert _is_stop(kind, sent[-1][1])
    # Hold the current heading: a zero rover vector would steer north.
    assert stops[0]["type_mask"] & IGNORE_YAW == 0
    assert stops[0]["yaw"] == pytest.approx(math.radians(HEADING_DEG))
    _cancel(vehicle)


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_setpoints_target_the_autopilot_not_mavsdk(api, kind, monkeypatch):
    """MAVSDK drops messages for a system it has no link to, so a setpoint
    addressed to its own GCS id (245) never reaches the vehicle."""
    monkeypatch.delenv("AP_EXPENV_MAV_SYSID", raising=False)
    monkeypatch.delenv("MAV_SYSID", raising=False)
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST), duration=0.2)
    await _wait_for_stop(kind, sent)

    assert sent
    assert {fields["target_system"] for _, fields in sent} == {AUTOPILOT_SYSID}


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_drone_velocity_faces_locked_heading(api, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, "drone", monkeypatch, system)
    vehicle._current_heading = 45.0

    await vehicle.set_velocity(vector_cls(*FIRST))
    await vehicle._stop()

    assert sent[0][1]["yaw"] == pytest.approx(math.radians(45.0))
    assert sent[0][1]["type_mask"] & IGNORE_YAW == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_new_velocity_replaces_old_without_stopping(api, kind, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.15)
    await vehicle.set_velocity(vector_cls(*SECOND), duration=5)
    first_second = next(i for i, (_, f) in enumerate(sent) if (f["vx"], f["vy"]) == SECOND[:2])
    await asyncio.sleep(0.2)

    tail = sent[first_second:]
    assert not any(_is_stop(kind, f) for _, f in sent), sent
    assert all((f["vx"], f["vy"]) == SECOND[:2] for _, f in tail), "old stream kept sending"
    await vehicle._stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_expiring_velocity_does_not_stop_newer_command(api, kind, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST), duration=0.05)
    await _wait_for_stop(kind, sent)
    await vehicle.set_velocity(vector_cls(*SECOND))
    await asyncio.sleep(0.3)

    last_second = max(i for i, (_, f) in enumerate(sent) if (f["vx"], f["vy"]) == SECOND[:2])
    assert not any(_is_stop(kind, f) for _, f in sent[last_second:]), sent
    _cancel(vehicle)


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_stop_ends_velocity_once_with_nothing_after(api, kind, monkeypatch):
    """A following movement command (via _stop) ends the stream in GUIDED."""
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.2)
    await vehicle._stop()
    count = len(sent)
    await asyncio.sleep(0.2)
    await vehicle._stop()

    assert len(sent) == count, "stream sent after it was stopped"
    assert _is_stop(kind, sent[-1][1]), sent
    assert sum(_is_stop(kind, f) for _, f in sent) == 1, sent
    assert system.offboard.method_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["drone", "rover"])
async def test_v2_stop_velocity_is_public(kind, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle("v2", kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await vehicle.stop_velocity()
    assert _is_stop(kind, sent[-1][1])
    assert vehicle.done_moving()


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_cancelled_stream_stops_the_vehicle(api, kind, monkeypatch):
    """Runner shutdown or close() cancels the task: don't leave the vehicle moving."""
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.1)
    _cancel(vehicle)
    await asyncio.gather(*vehicle._command_tasks, return_exceptions=True)

    assert _is_stop(kind, sent[-1][1]), sent


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_send_error_stops_the_vehicle(api, kind, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)
    calls = {"n": 0}
    record = system.mavlink_direct.send_message.side_effect

    async def flaky(msg):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("link hiccup")
        await record(msg)

    system.mavlink_direct.send_message.side_effect = flaky
    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.3)

    assert _is_stop(kind, sent[-1][1]), sent
    assert not vehicle._velocity.active


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
@pytest.mark.parametrize(
    ("vector", "duration"),
    [((math.nan, 0, 0), None), ((0, math.inf, 0), None), ((1, 0, 0), -1), ((1, 0, 0), math.nan)],
)
async def test_invalid_velocity_is_refused(api, kind, vector, duration, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    with pytest.raises(_velocity_error(api)):
        await vehicle.set_velocity(vector_cls(*vector), duration=duration)
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_zero_duration_stops_immediately(api, kind, monkeypatch):
    """duration=0 means stop right away, not hold forever."""
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST), duration=0)
    await asyncio.sleep(0.15)
    assert len(sent) == 2, sent
    assert _is_stop(kind, sent[-1][1])


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_rover_zero_vector_holds_heading(api, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, "rover", monkeypatch, system)

    await vehicle.set_velocity(vector_cls(0, 0, 0))
    await vehicle._stop()
    assert all(_is_stop("rover", f) for _, f in sent)
    assert sent[0][1]["yaw"] == pytest.approx(math.radians(HEADING_DEG))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["drone", "rover"])
async def test_v2_sync_close_stops_velocity(kind, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle("v2", kind, monkeypatch, system)
    tasks = []

    await vehicle.set_velocity(vector_cls(*FIRST))
    tasks.extend(vehicle._command_tasks)
    with pytest.warns(DeprecationWarning):
        vehicle.close()
    await asyncio.gather(*tasks, vehicle._close_task, return_exceptions=True)

    assert _is_stop(kind, sent[-1][1]), sent


@pytest.mark.parametrize("kind", ["drone", "rover"])
def test_v1_close_stops_velocity(kind, monkeypatch):
    """v1 close() stops the MAVSDK loop at once, so it sends the stop itself."""
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle("v1", kind, monkeypatch, system)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    vehicle._mavsdk_loop = loop
    vehicle._mavsdk_thread = thread

    async def scenario():
        await vehicle.set_velocity(vector_cls(*FIRST))
        vehicle._stop_velocity_on_close()
        count = len(sent)
        _cancel(vehicle)
        await asyncio.gather(*vehicle._command_tasks, return_exceptions=True)
        return count

    try:
        count = asyncio.run(scenario())
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
    assert _is_stop(kind, sent[count - 1][1]), sent
    assert len(sent) == count, "cancelled stream sent a second stop after close()"


@pytest.mark.asyncio
async def test_stream_stop_without_running_stream_sends_nothing():
    stream = VelocityStream(0.05)
    send = AsyncMock()
    await stream.stop(send, lambda: "stop")
    send.assert_not_called()


@pytest.mark.asyncio
async def test_stream_first_send_error_propagates():
    stream = VelocityStream(0.05)
    send = AsyncMock(side_effect=RuntimeError("no link"))
    with pytest.raises(RuntimeError):
        await stream.start(send, "go", lambda: "stop", None)
    assert not stream.active


def _slow_recording_system() -> tuple[MagicMock, list]:
    """Like _recording_system, but each send yields like a real gRPC call."""
    system, sent = _recording_system()
    record = system.mavlink_direct.send_message.side_effect

    async def slow(msg):
        await asyncio.sleep(0.01)
        await record(msg)

    system.mavlink_direct.send_message.side_effect = slow
    return system, sent


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_cancel_while_replacing_still_stops(api, kind, monkeypatch):
    """Cancelled while waiting for the old stream: nothing else would stop it."""
    system, sent = _slow_recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.12)
    replacing = asyncio.create_task(vehicle.set_velocity(vector_cls(*SECOND)))
    await asyncio.sleep(0)
    replacing.cancel()
    await asyncio.gather(replacing, return_exceptions=True)
    await asyncio.sleep(0.1)

    assert _is_stop(kind, sent[-1][1]), sent
    assert not vehicle._velocity.active


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_cancelled_stream_with_real_await_still_stops(api, kind, monkeypatch):
    system, sent = _slow_recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await asyncio.sleep(0.1)
    _cancel(vehicle)
    await asyncio.gather(*vehicle._command_tasks, return_exceptions=True)
    await asyncio.sleep(0.05)

    assert _is_stop(kind, sent[-1][1]), sent


@pytest.mark.asyncio
@pytest.mark.parametrize(("api", "kind"), CASES)
async def test_concurrent_set_velocity_leaves_one_stream(api, kind, monkeypatch):
    system, sent = _slow_recording_system()
    vehicle, vector_cls = _vehicle(api, kind, monkeypatch, system)

    await asyncio.gather(vehicle.set_velocity(vector_cls(*FIRST)), vehicle.set_velocity(vector_cls(*SECOND)))
    await asyncio.sleep(0.05)
    count = len(sent)
    await asyncio.sleep(0.2)

    tail = {(f["vx"], f["vy"]) for _, f in sent[count:]}
    assert len(tail) == 1, f"two streams running: {sent[count:]}"
    assert sum(not t.done() for t in vehicle._command_tasks) == 1
    await vehicle._stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_blocking_set_heading_ends_velocity(api, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, "drone", monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await vehicle.set_heading(HEADING_DEG)
    count = len(sent)
    await asyncio.sleep(0.15)

    targets = [f for name, f in sent if name == "SET_POSITION_TARGET_LOCAL_NED"]
    assert _is_stop("drone", targets[-1])
    assert sent[-1][0] == "COMMAND_LONG"
    assert len(sent) == count, "velocity stream kept overriding the yaw"


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["v1", "v2"])
async def test_non_blocking_set_heading_applies_to_next_velocity(api, monkeypatch):
    system, sent = _recording_system()
    vehicle, vector_cls = _vehicle(api, "drone", monkeypatch, system)

    await vehicle.set_velocity(vector_cls(*FIRST))
    await vehicle.set_heading(45.0, blocking=False)
    await vehicle.set_velocity(vector_cls(*SECOND))
    await vehicle._stop()

    second = next(f for _, f in sent if (f["vx"], f["vy"]) == SECOND[:2])
    assert second["yaw"] == pytest.approx(math.radians(45.0))
