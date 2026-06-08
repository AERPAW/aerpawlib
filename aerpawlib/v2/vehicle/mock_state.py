"""Shared default vehicle state for DummyVehicle and MockVehicle."""

from __future__ import annotations

from aerpawlib.v2.constants import GPS_3D_FIX_TYPE, MOCK_LAT, MOCK_LON

from .state import VehicleState


def default_mock_state() -> VehicleState:
    """Return a VehicleState pre-populated for dry-runs and unit tests."""
    state = VehicleState()
    state.update_position(MOCK_LAT, MOCK_LON, 0.0, 0.0)
    state.update_gps(GPS_3D_FIX_TYPE, 10)
    state.update_battery(12.6, 0.0, 100)
    state.update_home(MOCK_LAT, MOCK_LON, 0.0, 0.0)
    state.update_armable(
        global_ok=True,
        local_ok=True,
        home_ok=True,
        armable=True,
    )
    return state
