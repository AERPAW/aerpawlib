import pytest

from aerpawlib.v1.safety import (
    SafetyCheckerServer,
    deserialize_msg,
    serialize_request,
)


class _FakeSocket:
    def __init__(self):
        self._recv_count = 0
        self.sent = []

    def bind(self, _addr):
        return None

    def recv(self):
        self._recv_count += 1
        if self._recv_count == 1:
            # Not valid compressed payload; deserialize_msg should fail.
            return b"not-a-zlib-payload"
        raise KeyboardInterrupt()

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        return None


class _FakeContext:
    def __init__(self, socket_obj):
        self._socket_obj = socket_obj

    def socket(self, _socket_type):
        return self._socket_obj

    def term(self):
        return None


def test_start_server_handles_malformed_request_without_crashing():
    fake_socket = _FakeSocket()
    fake_context = _FakeContext(fake_socket)

    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.REQUEST_FUNCTIONS = {}

    with pytest.raises(KeyboardInterrupt):
        server.start_server(14580, context_factory=lambda: fake_context)

    assert len(fake_socket.sent) == 1
    response = deserialize_msg(fake_socket.sent[0])
    assert response["result"] is False
    assert "Server error" in response["message"]


class _UnknownFunctionSocket:
    def __init__(self):
        self._recv_count = 0
        self.sent = []

    def bind(self, _addr):
        return None

    def recv(self):
        self._recv_count += 1
        if self._recv_count == 1:
            return serialize_request("not_implemented", [])
        raise KeyboardInterrupt()

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        return None


def test_start_server_unknown_function_request_does_not_crash():
    fake_socket = _UnknownFunctionSocket()
    fake_context = _FakeContext(fake_socket)

    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.REQUEST_FUNCTIONS = {}

    with pytest.raises(KeyboardInterrupt):
        server.start_server(14581, context_factory=lambda: fake_context)

    assert len(fake_socket.sent) == 1
    response = deserialize_msg(fake_socket.sent[0])
    assert response["result"] is False
    assert "not_implemented" in response["message"]


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
