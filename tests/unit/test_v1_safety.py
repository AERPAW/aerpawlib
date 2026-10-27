import pytest

from aerpawlib.v1.safety import (
    SafetyCheckerServer,
    deserialize_msg,
    serialize_request,
)


class _FakeSocket:
    """A REP socket that has the given requests waiting."""

    def __init__(self, *requests):
        self._requests = list(requests)
        self.bound = []
        self.sent = []

    def bind(self, addr):
        self.bound.append(addr)

    def recv(self):
        return self._requests.pop(0)

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        return None


class _FakeContext:
    def __init__(self, *sockets):
        self._sockets = list(sockets)

    def socket(self, _socket_type):
        return self._sockets.pop(0)

    def term(self):
        return None


class _FakePoller:
    """Reports every registered socket ready once, then stops the loop."""

    def __init__(self):
        self.registered = []
        self._polled = False

    def register(self, socket, _flags):
        self.registered.append(socket)

    def poll(self):
        if self._polled:
            raise KeyboardInterrupt()
        self._polled = True
        return [(socket, 1) for socket in self.registered]


def _reporting_server():
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.takeoff_location = None
    server.taken_over_reason = None
    server.REQUEST_FUNCTIONS = {"report_takeover_req": server.report_takeover_handler}
    return server


def _reply(socket):
    assert len(socket.sent) == 1
    return deserialize_msg(socket.sent[0])


def test_handle_request_answers_a_malformed_request():
    socket = _FakeSocket(b"not-a-zlib-payload")
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.REQUEST_FUNCTIONS = {}

    server.handle_request(socket, from_filter=False)

    response = _reply(socket)
    assert response["result"] is False
    assert "Server error" in response["message"]


def test_handle_request_answers_an_unknown_request():
    socket = _FakeSocket(serialize_request("not_implemented", []))
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.REQUEST_FUNCTIONS = {}

    server.handle_request(socket, from_filter=False)

    response = _reply(socket)
    assert response["result"] is False
    assert "not_implemented" in response["message"]


@pytest.mark.parametrize("request_function", sorted(SafetyCheckerServer.FILTER_ONLY_REQUESTS))
def test_evm_port_refuses_filter_reports(request_function):
    socket = _FakeSocket(serialize_request(request_function, [None, None]))
    server = _reporting_server()
    server.report_takeover("mode LOITER (operator)")

    server.handle_request(socket, from_filter=False)

    response = _reply(socket)
    assert response["result"] is False
    assert "only from the C-VM filter" in response["message"]
    assert server.taken_over_reason == "mode LOITER (operator)"


def test_filter_port_accepts_filter_reports():
    socket = _FakeSocket(serialize_request("report_takeover_req", ["mode LOITER (operator)"]))
    server = _reporting_server()

    server.handle_request(socket, from_filter=True)

    assert _reply(socket)["result"] is True
    assert server.taken_over_reason == "mode LOITER (operator)"


def test_start_server_binds_the_filter_port_to_loopback_and_serves_both():
    evm_socket = _FakeSocket(serialize_request("report_takeover_req", [None]))
    filter_socket = _FakeSocket(serialize_request("report_takeover_req", ["mode LOITER (operator)"]))
    server = _reporting_server()

    with pytest.raises(KeyboardInterrupt):
        server.start_server(
            14580,
            14581,
            context_factory=lambda: _FakeContext(evm_socket, filter_socket),
            poller_factory=_FakePoller,
        )

    assert evm_socket.bound == ["tcp://*:14580"]
    assert filter_socket.bound == ["tcp://127.0.0.1:14581"]
    assert _reply(filter_socket)["result"] is True
    assert _reply(evm_socket)["result"] is False
    assert server.taken_over_reason == "mode LOITER (operator)"


def _copter_server(min_takeoff_alt=20):
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.vehicle_type = "copter"
    server.min_alt = 20
    server.min_takeoff_alt = min_takeoff_alt
    server.max_alt = 120
    server.include_geofences = [
        [
            {"lat": 35.72, "lon": -78.70},
            {"lat": 35.74, "lon": -78.70},
            {"lat": 35.74, "lon": -78.69},
            {"lat": 35.72, "lon": -78.69},
        ],
    ]
    server.exclude_geofences = []
    server.takeoff_location = None
    server.taken_over_reason = None
    server.filter_abort_reason = None
    server.filter_abort_time = None
    return server


def _copter_config(**overrides):
    config = {
        "vehicle_type": "copter",
        "max_speed": 20,
        "min_speed": 1,
        "include_geofences": [],
        "exclude_geofences": [],
        "max_alt": 120,
        "min_alt": 20,
    }
    config.update(overrides)
    return config


def test_validate_takeoff_does_not_record_pad():
    server = _copter_server()
    ok, _msg = server.validate_takeoff_command(25.0, 35.729, -78.697)
    assert ok is True
    assert server.takeoff_location is None


def test_takeoff_below_min_takeoff_alt_is_rejected():
    # 22 m is above min_alt but below the takeoff floor.
    server = _copter_server(min_takeoff_alt=25)
    ok, msg = server.validate_takeoff_command(22.0, 35.729, -78.697)
    assert ok is False
    assert "25" in msg
    ok, _msg = server.validate_takeoff_command(25.0, 35.729, -78.697)
    assert ok is True


def test_get_limitations_reports_min_takeoff_alt():
    server = _copter_server(min_takeoff_alt=25)
    server.min_speed = 1
    server.max_speed = 20
    server.max_vertical_speed = 5
    assert server.get_limitations()["min_takeoff_alt"] == 25


def test_config_accepts_min_takeoff_alt_within_limits():
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.validate_config(_copter_config(min_takeoff_alt=25), "copter.yaml")
    server.validate_config(_copter_config(), "copter.yaml")


@pytest.mark.parametrize("value", [10, 130, float("nan")])
def test_config_rejects_min_takeoff_alt_outside_limits(value):
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    with pytest.raises(Exception, match="min_takeoff_alt"):
        server.validate_config(_copter_config(min_takeoff_alt=value), "copter.yaml")


def _velocity_server(vehicle_type="copter"):
    server = _copter_server()
    server.vehicle_type = vehicle_type
    server.max_speed = 20
    server.max_vertical_speed = 5
    server.taken_over_reason = None
    return server


# Near the middle of the fence; the east edge (-78.69) is ~900 m away.
_HERE = (35.73, -78.695)


def _here(alt=30.0):
    from aerpawlib.v1.util import Coordinate

    return Coordinate(_HERE[0], _HERE[1], alt)


def _v(north, east, down):
    from aerpawlib.v1.util import VectorNED

    return VectorNED(north, east, down)


def test_landing_checks_the_pad_the_filter_reported():
    server = _velocity_server()
    assert server.validate_landing_command(*_HERE)[0] is True  # no pad yet
    assert server.report_takeoff_location(*_HERE) == (True, "")
    near = _here() + _v(0, 4.5, 0)
    far = _here() + _v(0, 6, 0)
    assert server.validate_landing_command(near.lat, near.lon)[0] is True
    ok, msg = server.validate_landing_command(far.lat, far.lon)
    assert ok is False
    assert "5 meters" in msg
    assert server.report_takeoff_location(None, None) == (True, "")
    assert server.validate_landing_command(far.lat, far.lon)[0] is True


def test_report_takeoff_location_rejects_non_finite():
    server = _velocity_server()
    ok, _msg = server.report_takeoff_location(float("nan"), -78.695)
    assert ok is False
    assert server.takeoff_location is None


def test_takeover_refuses_guided_commands_and_velocity_until_cleared():
    from aerpawlib.v1.constants import TAKEN_OVER_MESSAGE

    server = _velocity_server()
    assert server.validate_guided_command() == (True, "")
    server.report_takeover("mode LOITER (operator)")
    ok, msg = server.validate_guided_command()
    assert ok is False
    assert msg.startswith(TAKEN_OVER_MESSAGE)
    assert "LOITER" in msg
    ok, msg = server.validate_velocity_command(_here(), _v(0, 0, 0))
    assert ok is False
    assert msg.startswith(TAKEN_OVER_MESSAGE)
    # The filter's own geofence checks of the vehicle's track still pass.
    assert server.validate_waypoint_command(_here(), _here() + _v(5, 0, 0))[0] is True
    server.report_takeover(None)
    assert server.validate_guided_command() == (True, "")


def test_velocity_speed_limits():
    server = _velocity_server()
    assert server.validate_velocity_command(_here(), _v(20, 0, 0))[0] is True
    assert server.validate_velocity_command(_here(), _v(16, 12.1, 0))[0] is False
    assert server.validate_velocity_command(_here(60), _v(0, 0, 5))[0] is True
    ok, msg = server.validate_velocity_command(_here(60), _v(0, 0, 5.5))
    assert ok is False
    assert "Vertical" in msg
    ok, _msg = server.validate_velocity_command(_here(), _v(float("nan"), 0, 0))
    assert ok is False


def test_velocity_look_ahead_leaving_the_fence_is_refused():
    server = _velocity_server()
    near_east_edge = _here() + _v(0, 440, 0)  # ~10 m inside the east edge
    assert server.validate_velocity_command(near_east_edge, _v(0, 2, 0))[0] is True
    ok, msg = server.validate_velocity_command(near_east_edge, _v(0, 5, 0))
    assert ok is False
    assert "geofence" in msg


def test_velocity_look_ahead_uses_real_altitude_and_margin():
    server = _velocity_server()
    # 3 m/s down from 56 m stays far above min_alt (the 2021 filter predicted 18 m).
    assert server.validate_velocity_command(_here(56), _v(0, 0, 3))[0] is True
    # 1 m/s down from 22 m predicts 18 m: inside the 2 m margin below min_alt.
    assert server.validate_velocity_command(_here(22), _v(0, 0, 1))[0] is True
    assert server.validate_velocity_command(_here(22), _v(0, 0, 2))[0] is False


def test_rover_velocity_ignores_vz():
    server = _velocity_server(vehicle_type="rover")
    assert server.validate_velocity_command(_here(0), _v(1, 0, 9))[0] is True


def _v1_client(replies: list):
    from aerpawlib.v1.safety import SafetyCheckerClient

    client = SafetyCheckerClient.__new__(SafetyCheckerClient)
    client.sent = []

    def send_request(msg):
        request = deserialize_msg(msg)
        client.sent.append((request["request_function"], request["params"]))
        return replies.pop(0)

    client.send_request = send_request
    return client


def test_v1_client_sends_the_new_requests():
    client = _v1_client(
        [
            {"result": False, "message": "too fast"},
            {"result": True, "message": ""},
            {"result": True, "message": ""},
            {"result": True, "message": ""},
        ],
    )
    assert client.validate_velocity_command(_here(), _v(30, 0, 0)) == (False, "too fast")
    assert client.validate_guided_command() == (True, "")
    assert client.report_takeoff_location(*_HERE) == (True, "")
    assert client.report_takeover(None) == (True, "")
    names = [name for name, _ in client.sent]
    assert names == ["validate_velocity_req", "validate_guided_command_req", "report_takeoff_location_req", "report_takeover_req"]
    assert client.sent[0][1][1:] == [30, 0, 0]


@pytest.mark.asyncio
async def test_v2_client_sends_the_new_requests():
    import json
    import zlib

    from aerpawlib.v2.safety import SafetyCheckerClient
    from aerpawlib.v2.types import Coordinate, VectorNED

    client = SafetyCheckerClient.__new__(SafetyCheckerClient)
    sent = []
    status = {"aborted": True, "reason": "geofence", "age_s": 1.0}

    async def send_raw(msg):
        sent.append(json.loads(zlib.decompress(msg))["request_function"])
        return {"result": True, "message": "", "data": status}

    client._send_raw = send_raw
    assert await client.validate_guided_command() == (True, "")
    assert await client.validate_velocity(Coordinate(*_HERE, 30), VectorNED(1, 0, 0)) == (True, "")
    assert await client.get_filter_status() == status
    assert sent == ["validate_guided_command_req", "validate_velocity_req", "get_filter_status_req"]


def test_filter_abort_is_recorded_and_cleared():
    server = _velocity_server()
    assert server.get_filter_status() == {"aborted": False, "reason": None, "age_s": None}
    assert server.report_filter_abort("Mode 5 not allowed.") == (True, "")
    status = server.get_filter_status()
    assert status["aborted"] is True
    assert status["reason"] == "Mode 5 not allowed."
    assert status["age_s"] >= 0
    reply = deserialize_msg(server.get_filter_status_handler())
    assert reply["data"]["reason"] == "Mode 5 not allowed."
    server.report_filter_abort(None)
    assert server.get_filter_status()["aborted"] is False


def test_v1_client_filter_status():
    status = {"aborted": True, "reason": "geofence", "age_s": 1.0}
    client = _v1_client([{"result": True, "message": "", "data": status}, {"result": True, "message": ""}])
    assert client.get_filter_status() == status
    assert client.report_filter_abort(None) == (True, "")
    assert [name for name, _ in client.sent] == ["get_filter_status_req", "report_filter_abort_req"]
