from types import SimpleNamespace

from aerpawlib._internal.connection_string import (
    normalize_mavsdk_connection_string,
    parse_udp_connection_port,
)
from aerpawlib._internal.mavlink_ids import autopilot_sysid, resolve_mav_sysid


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


def test_resolve_mav_sysid_uses_vehicle_sysid(monkeypatch):
    monkeypatch.delenv("AP_EXPENV_MAV_SYSID", raising=False)
    monkeypatch.delenv("MAV_SYSID", raising=False)
    assert resolve_mav_sysid(7) == 7
    assert resolve_mav_sysid(None) == 1
    monkeypatch.setenv("MAV_SYSID", "17")
    assert resolve_mav_sysid(7) == 17


def test_autopilot_sysid_only_from_autopilot_component():
    assert autopilot_sysid(SimpleNamespace(system_id=3, component_id=1)) == 3
    # A GCS or companion (e.g. MAVSDK's own 245/190) is not the vehicle.
    assert autopilot_sysid(SimpleNamespace(system_id=245, component_id=190)) is None
