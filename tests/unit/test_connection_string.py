from aerpawlib._internal.connection_string import (
    normalize_mavsdk_connection_string,
    parse_udp_connection_port,
)
from aerpawlib._internal.mavlink_ids import resolve_mav_sysid


def test_normalize_udp_slash_and_dronekit():
    assert normalize_mavsdk_connection_string("udp://127.0.0.1:14550") == "udpin://127.0.0.1:14550"
    assert normalize_mavsdk_connection_string("udp:127.0.0.1:14550") == "udpin://127.0.0.1:14550"
    assert normalize_mavsdk_connection_string("udpin://127.0.0.1:14550") == "udpin://127.0.0.1:14550"
    assert normalize_mavsdk_connection_string("/dev/ttyACM0") == "/dev/ttyACM0"


def test_parse_normalized_udp():
    assert parse_udp_connection_port("udpin://127.0.0.1:14550") == ("127.0.0.1", 14550)


def test_resolve_mav_sysid_env(monkeypatch):
    monkeypatch.setenv("MAV_SYSID", "17")
    assert resolve_mav_sysid() == 17
    monkeypatch.setenv("AP_EXPENV_MAV_SYSID", "4")
    assert resolve_mav_sysid() == 4
    monkeypatch.delenv("AP_EXPENV_MAV_SYSID")
    monkeypatch.delenv("MAV_SYSID")
    assert resolve_mav_sysid() == 1
