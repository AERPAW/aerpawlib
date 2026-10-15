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


def test_validate_takeoff_does_not_record_pad():
    server = _copter_server()
    ok, _msg = server.validate_takeoff_command(25.0, 35.73, -78.695)
    assert ok is True
    assert server.takeoff_location is None


def _copter_server():
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    server.vehicle_type = "copter"
    server.min_speed = 0
    server.max_speed = 10
    server.min_alt = 20
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


def _waypoint_json(alt, lat=35.73, lon=-78.695):
    from aerpawlib.v1.util import Coordinate

    return Coordinate(lat, lon, alt).to_json()


def test_get_limitations_handler_returns_copter_limits():
    response = deserialize_msg(_copter_server().get_limitations_handler())
    assert response["result"] is True
    assert response["data"] == {
        "vehicle_type": "copter",
        "min_speed": 0,
        "max_speed": 10,
        "min_alt": 20,
        "max_alt": 120,
    }


def test_get_limitations_rover_has_no_altitudes():
    server = _copter_server()
    server.vehicle_type = "rover"
    del server.min_alt, server.max_alt
    limits = server.get_limitations()
    assert limits["min_alt"] is None
    assert limits["max_alt"] is None


def test_responses_without_data_keep_wire_format():
    from aerpawlib.v1.safety import serialize_response

    assert "data" not in deserialize_msg(serialize_response("x", result=True))


@pytest.mark.parametrize("alt", [5.0, 150.0])
def test_waypoint_altitude_limits_skipped_only_with_flag(alt):
    server = _copter_server()
    response = deserialize_msg(server.validate_waypoint_handler(_waypoint_json(alt), _waypoint_json(alt)))
    assert response["result"] is False
    assert "Altitude" in response["message"]

    response = deserialize_msg(server.validate_waypoint_handler(_waypoint_json(alt), _waypoint_json(alt), True))
    assert response["result"] is True


def test_waypoint_flag_still_enforces_geofence():
    server = _copter_server()
    response = deserialize_msg(
        server.validate_waypoint_handler(_waypoint_json(5.0), _waypoint_json(5.0, lat=36.0), True),
    )
    assert response["result"] is False
    assert "outside of the geofence" in response["message"]


@pytest.mark.parametrize("flag", ["true", 1, "yes"])
def test_waypoint_flag_must_be_literal_true(flag):
    """A malformed flag must not skip the altitude limits (fail closed)."""
    server = _copter_server()
    response = deserialize_msg(server.validate_waypoint_handler(_waypoint_json(5.0), _waypoint_json(5.0), flag))
    assert response["result"] is False


def test_client_sends_flag_only_when_set():
    from aerpawlib.v1.safety import SafetyCheckerClient
    from aerpawlib.v1.util import Coordinate

    client = SafetyCheckerClient.__new__(SafetyCheckerClient)
    sent = []
    client.send_request = lambda msg: sent.append(deserialize_msg(msg)) or {"result": True, "message": ""}
    loc = Coordinate(35.73, -78.695, 30)

    client.validate_waypoint_command(loc, loc)
    client.validateWaypointCommand(loc, loc, True)
    assert len(sent[0]["params"]) == 2
    assert sent[1]["params"][2] is True


def test_client_get_limitations():
    from aerpawlib.v1.safety import SafetyCheckerClient

    client = SafetyCheckerClient.__new__(SafetyCheckerClient)
    client.send_request = lambda _msg: {"result": True, "message": "", "data": {"min_alt": 20}}
    assert client.getLimitations() == {"min_alt": 20}

    client.send_request = lambda _msg: {"result": False, "message": "Unimplemented"}
    with pytest.raises(RuntimeError):
        client.get_limitations()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "25", None, True])
def test_non_finite_takeoff_and_speed_rejected(value):
    """NaN compares false against every limit, so it must be rejected explicitly."""
    server = _copter_server()
    assert server.validate_takeoff_command(value, 35.73, -78.695)[0] is False
    assert server.validate_change_speed_command(value)[0] is False


@pytest.mark.parametrize("field", ["lat", "lon", "alt"])
def test_non_finite_waypoint_rejected(field):
    from aerpawlib.v1.util import Coordinate

    server = _copter_server()
    good = Coordinate(35.73, -78.695, 30)
    bad = Coordinate(35.73, -78.695, 30)
    setattr(bad, field, float("nan"))
    ok, msg = server.validate_waypoint_command(good, bad)
    assert ok is False
    assert "finite" in msg
    ok, _ = server.validate_waypoint_command(good, bad, taking_off_or_landing=True)
    assert ok is False


def test_takeoff_outside_geofence_rejected():
    server = _copter_server()
    assert server.validate_takeoff_command(25.0, 35.73, -78.695)[0] is True
    assert server.validate_takeoff_command(25.0, 0.0, 10.0)[0] is False
    assert server.validate_takeoff_command(25.0, float("nan"), -78.695)[0] is False


def test_takeoff_inside_no_go_zone_rejected():
    server = _copter_server()
    server.exclude_geofences = [
        [
            {"lat": 35.729, "lon": -78.696},
            {"lat": 35.731, "lon": -78.696},
            {"lat": 35.731, "lon": -78.694},
            {"lat": 35.729, "lon": -78.694},
        ],
    ]
    assert server.validate_takeoff_command(25.0, 35.73, -78.695)[0] is False


def test_landing_nan_location_rejected_with_pad():
    from aerpawlib.v1.util import Coordinate

    server = _copter_server()
    server.takeoff_location = Coordinate(35.73, -78.695, 0)
    assert server.validate_landing_command(float("nan"), float("nan"))[0] is False


@pytest.mark.parametrize(
    ("overrides", "ok"),
    [
        ({}, True),
        ({"min_alt": float("nan")}, False),
        ({"max_alt": float("inf")}, False),
        ({"min_alt": 130}, False),
        ({"max_speed": "20"}, False),
        ({"min_speed": 30}, False),
    ],
)
def test_validate_config_limits(overrides, ok):
    config = {
        "vehicle_type": "copter",
        "max_speed": 20,
        "min_speed": 1,
        "max_alt": 120,
        "min_alt": 20,
        "include_geofences": [],
        "exclude_geofences": [],
        **overrides,
    }
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    if ok:
        server.validate_config(config, "cfg.yaml")
    else:
        with pytest.raises(Exception, match="finite numbers"):
            server.validate_config(config, "cfg.yaml")


def test_real_copter_configs_still_validate():
    import pathlib

    import yaml

    geofences = pathlib.Path(__file__).resolve().parents[6] / "C-VM" / "MAVLink_Filter" / "Geofences"
    configs = sorted(geofences.glob("safety_checker_config_*.yaml"))
    if not configs:
        pytest.skip("AHN geofence configs not available outside AERPAW-Dev")
    server = SafetyCheckerServer.__new__(SafetyCheckerServer)
    for path in configs:
        server.validate_config(yaml.safe_load(path.read_text()), str(path))
