"""
Pytest configuration and fixtures for aerpawlib tests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Type, TypeVar

import pytest
import pytest_asyncio

from aerpawlib.v1.exceptions import ConnectionTimeoutError
from aerpawlib.v1.util import Coordinate, VectorNED
from aerpawlib.v1.vehicle import Drone, Rover, Vehicle

# Constants
DEFAULT_SITL_PORT = 14550
SITL_GPS_TIMEOUT = 120  # Overall timeout for connection + GPS fix

# AERPAW Lake Wheeler site coordinates
LAKE_WHEELER_LAT = 35.727436
LAKE_WHEELER_LON = -78.696587

V = TypeVar("V", bound=Vehicle)

def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options."""
    parser.addoption(
        "--sitl-port",
        action="store",
        default=str(DEFAULT_SITL_PORT),
        help=f"UDP port for SITL connection (default: {DEFAULT_SITL_PORT})",
    )

def pytest_configure(config: pytest.Config) -> None:
    """Additional pytest configuration."""
    # Ensure logs from aerpawlib are visible during test failures
    logging.getLogger("aerpawlib").setLevel(logging.DEBUG)

def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply markers based on test directory."""
    for item in items:
        path_str = str(item.path)
        if "/unit/" in path_str:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in path_str:
            item.add_marker(pytest.mark.integration)

# Utility Fixtures

@pytest.fixture
def origin_coordinate():
    return Coordinate(LAKE_WHEELER_LAT, LAKE_WHEELER_LON, 0)

@pytest.fixture
def nearby_coordinate():
    return Coordinate(LAKE_WHEELER_LAT + 0.0009, LAKE_WHEELER_LON, 0)

@pytest.fixture
def zero_vector():
    return VectorNED(0, 0, 0)

# SITL Connection Fixtures

@pytest.fixture(scope="session")
def sitl_connection_string(request: pytest.FixtureRequest) -> str:
    port = request.config.getoption("--sitl-port")
    # Using udpin (listening) as it is often more robust for SITL
    # where the simulation might restart and reconnect.
    return f"udpin://127.0.0.1:{port}"

async def _connect_and_wait(
    vehicle_class: Type[V],
    connection_string: str,
    timeout: int = SITL_GPS_TIMEOUT
) -> V:
    """
    Helper to connect to a vehicle and wait for it to be ready.
    Provides detailed error messages on failure.
    """
    print(f"\n[SITL] Connecting to {vehicle_class.__name__} at {connection_string}...")

    try:
        # Create vehicle in a thread because its constructor is blocking (starts its own event loop)
        vehicle = await asyncio.to_thread(vehicle_class, connection_string)
    except ConnectionTimeoutError:
        pytest.fail(
            f"\n\nCONNECTION FAILED: Timed out connecting to {vehicle_class.__name__} at {connection_string}.\n\n"
            f"Is SITL (ArduPilot/PX4) running and exporting MAVLink to this address?\n"
            f"If using sim_vehicle.py, ensure you have something like '--out=udp:127.0.0.1:{connection_string.split(':')[-1]}' in your command.\n"
        )
    except Exception as e:
        pytest.fail(f"\n\nINITIALIZATION FAILED: Error creating {vehicle_class.__name__}: {type(e).__name__}: {e}")

    print(f"[SITL] Connected. Waiting up to {timeout}s for 3D GPS fix...")

    # Wait for GPS fix (fix_type >= 3 = 3D fix)
    start = time.monotonic()
    last_fix = -1
    while time.monotonic() - start < timeout:
        current_fix = vehicle.gps.fix_type
        if current_fix != last_fix:
            print(f"  - GPS Status: {current_fix} (satellites: {vehicle.gps.satellites_visible})")
            last_fix = current_fix

        if current_fix >= 3:
            print("[SITL] GPS Fix acquired. Vehicle ready.")
            return vehicle
        await asyncio.sleep(1.0)

    # Timeout reached
    fix_type = vehicle.gps.fix_type
    sats = vehicle.gps.satellites_visible
    vehicle.close()

    pytest.fail(
        f"\n\nGPS FIX FAILED: {vehicle_class.__name__} failed to acquire 3D GPS fix within {timeout}s.\n"
        f"Last status: fix_type={fix_type}, satellites={sats}\n"
        f"Suggestion: Check SITL origin/home location and ensure it has enough time to initialize.\n"
    )

async def _full_sitl_reset(vehicle: Vehicle) -> None:
    """
    Performs a full SITL reset.
    Reboot alone is often not sufficient as it doesn't clear missions
    or geofences from ArduPilot's EEPROM.
    """
    print(f"\n[Cleanup] Performing full SITL reset for {type(vehicle).__name__}...")

    system = vehicle._system
    if not system:
        return

    async def _cleanup_steps():
        # 1. Clear Mission
        try:
            await system.mission.clear_mission()
            print("  - Mission cleared")
        except Exception as e:
            print(f"  - Mission clear failed: {e}")

        # 2. Clear Geofence
        try:
            await system.geofence.clear_geofence()
            print("  - Geofence cleared")
        except Exception:
            # Geofence plugin might not be supported on all vehicles
            pass

        # 3. Disarm (force if needed)
        try:
            await system.action.disarm()
            print("  - Disarmed")
        except Exception:
            pass

        # 4. Reboot
        try:
            await system.action.reboot()
            print("  - Rebooting SITL...")
        except Exception as e:
            print(f"  - Reboot failed: {e}")

    try:
        await vehicle._run_on_mavsdk_loop(_cleanup_steps())
        # Give it a moment to initiate the reboot before closing
        await asyncio.sleep(2)
    except Exception as e:
        print(f"Warning: Full SITL reset failed: {e}")

@pytest_asyncio.fixture(scope="function")
async def connected_drone(
    sitl_connection_string: str,
) -> AsyncGenerator[Drone, None]:
    """
    Provide a connected Drone instance for integration testing.
    """
    drone = await _connect_and_wait(Drone, sitl_connection_string)

    yield drone

    try:
        await _full_sitl_reset(drone)
    finally:
        drone.close()

@pytest_asyncio.fixture(scope="function")
async def connected_rover(
    sitl_connection_string: str,
) -> AsyncGenerator[Rover, None]:
    """
    Provide a connected Rover instance for integration testing.
    """
    rover = await _connect_and_wait(Rover, sitl_connection_string)

    yield rover

    try:
        await _full_sitl_reset(rover)
    finally:
        rover.close()

