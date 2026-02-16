"""
Pytest configuration and fixtures for aerpawlib v1 tests.

SITL is managed by pytest: started before integration tests, stopped after.
Full SITL reset (disarm, clear mission, battery reset) runs between each test.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

import pytest
import pytest_asyncio

# Constants
DEFAULT_SITL_PORT = 14550
SITL_STARTUP_TIMEOUT = 90
SITL_GPS_TIMEOUT = 120
LAKE_WHEELER_LAT = 35.727436
LAKE_WHEELER_LON = -78.696587


def _find_sim_vehicle() -> Optional[Path]:
    """Locate sim_vehicle.py from ARDUPILOT_HOME or common paths."""
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        os.environ.get("ARDUPILOT_HOME"),
        project_root / "ardupilot",
        project_root / "ardupilot-4.6.3",
    ]
    for base in candidates:
        if base is None:
            continue
        base = Path(base)
        script = base / "Tools" / "autotest" / "sim_vehicle.py"
        if script.exists():
            return script
    return None


def _port_available(host: str, port: int) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect((host, port))
        return True
    except (socket.error, OSError):
        return False


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options."""
    parser.addoption(
        "--sitl-port",
        action="store",
        default=str(DEFAULT_SITL_PORT),
        help=f"UDP port for SITL (default: {DEFAULT_SITL_PORT})",
    )
    parser.addoption(
        "--no-sitl",
        action="store_true",
        help="Skip SITL-managed integration tests (SITL must be running externally)",
    )
    parser.addoption(
        "--sitl-manage",
        action="store_true",
        default=True,
        help="Pytest starts/stops SITL for integration tests (default: True)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration."""
    logging.getLogger("aerpawlib").setLevel(logging.DEBUG)


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Auto-apply markers based on test path."""
    for item in items:
        path_str = str(item.path)
        if "/unit/" in path_str:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in path_str:
            item.add_marker(pytest.mark.integration)


# ---------------------------------------------------------------------------
# Unit test fixtures (no SITL)
# ---------------------------------------------------------------------------


@pytest.fixture
def origin_coordinate():
    """Coordinate at AERPAW Lake Wheeler."""
    from aerpawlib.v1.util import Coordinate
    return Coordinate(LAKE_WHEELER_LAT, LAKE_WHEELER_LON, 0)


@pytest.fixture
def nearby_coordinate():
    """Coordinate ~100m north of origin."""
    from aerpawlib.v1.util import Coordinate
    return Coordinate(LAKE_WHEELER_LAT + 0.0009, LAKE_WHEELER_LON, 0)


@pytest.fixture
def zero_vector():
    """Zero VectorNED."""
    from aerpawlib.v1.util import VectorNED
    return VectorNED(0, 0, 0)


# ---------------------------------------------------------------------------
# SITL management
# ---------------------------------------------------------------------------


class SITLManager:
    """
    Manages ArduPilot SITL process for integration tests.
    Starts SITL, provides connection string, performs full reset between tests.
    """

    def __init__(self, port: int, manage: bool = True):
        self.port = port
        self.manage = manage
        self._process: Optional[subprocess.Popen] = None
        self._sim_vehicle_path: Optional[Path] = None

    def start(self) -> str:
        """Start SITL and return connection string."""
        if not self.manage:
            return f"udpin://127.0.0.1:{self.port}"

        sim_vehicle = _find_sim_vehicle()
        if sim_vehicle is None:
            pytest.skip(
                "sim_vehicle.py not found. Set ARDUPILOT_HOME or run install_ardupilot.sh"
            )

        self._sim_vehicle_path = sim_vehicle
        ardupilot_home = sim_vehicle.parent.parent.parent

        env = os.environ.copy()
        env["ARDUPILOT_HOME"] = str(ardupilot_home)
        env.setdefault("SIM_SPEEDUP", "5")

        cmd = [
            sys.executable,
            str(sim_vehicle),
            "-v", "ArduCopter",
            "--out", f"udp:127.0.0.1:{self.port}",
            "--no-mavproxy",
            "-w",
        ]

        print(f"\n[SITL] Starting ArduPilot SITL on port {self.port}...")
        self._process = subprocess.Popen(
            cmd,
            cwd=str(ardupilot_home),
            env=env,
            stdout=subprocess.DEVNULL if not os.environ.get("SITL_VERBOSE") else None,
            stderr=subprocess.STDOUT if not os.environ.get("SITL_VERBOSE") else None,
        )

        # Wait for MAVLink port
        start = time.monotonic()
        while time.monotonic() - start < SITL_STARTUP_TIMEOUT:
            if _port_available("127.0.0.1", self.port):
                print(f"[SITL] Ready on udpin://127.0.0.1:{self.port}")
                return f"udpin://127.0.0.1:{self.port}"
            time.sleep(1)

        self.stop()
        pytest.fail(f"SITL failed to start within {SITL_STARTUP_TIMEOUT}s")

    def stop(self) -> None:
        """Stop SITL process."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            print("[SITL] Stopped")

    def connection_string(self) -> str:
        """Return MAVLink connection string."""
        return f"udpin://127.0.0.1:{self.port}"


# Session-scoped SITL: started once, shared across all integration tests
@pytest.fixture(scope="session")
def sitl_manager(request: pytest.FixtureRequest) -> SITLManager:
    """Session-scoped SITL manager. Starts SITL once for all integration tests."""
    port = int(request.config.getoption("--sitl-port", default=DEFAULT_SITL_PORT))
    no_sitl = request.config.getoption("--no-sitl", default=False)
    manage = request.config.getoption("--sitl-manage", default=True) and not no_sitl

    manager = SITLManager(port=port, manage=manage)
    if manage:
        manager.start()
        request.addfinalizer(manager.stop)
    return manager


@pytest.fixture
def sitl_connection_string(sitl_manager: SITLManager) -> str:
    """Connection string for SITL."""
    return sitl_manager.connection_string()


# ---------------------------------------------------------------------------
# Full SITL reset (between each integration test)
# ---------------------------------------------------------------------------


async def _full_sitl_reset(vehicle) -> None:
    """Disarm, clear mission, battery reset. Full clean state between tests."""
    from mavsdk.mavlink_direct import MavlinkMessage

    system = getattr(vehicle, "_system", None)
    if not system:
        return

    async def _reset():
        try:
            await system.mission.clear_mission()
        except Exception:
            pass
        try:
            await system.geofence.clear_geofence()
        except Exception:
            pass
        try:
            await system.action.return_to_launch()
            await asyncio.sleep(2)
        except Exception:
            pass
        try:
            fields = {
                "target_system": 1, "target_component": 1,
                "command": 501, "confirmation": 0,
                "param1": 1.0, "param2": 100.0,
                "param3": 0.0, "param4": 0.0,
                "param5": 0.0, "param6": 0.0, "param7": 0.0,
            }
            msg = MavlinkMessage(
                system_id=1, component_id=1,
                target_system_id=1, target_component_id=1,
                message_name="COMMAND_LONG",
                fields_json=json.dumps(fields),
            )
            await system.mavlink_direct.send_message(msg)
        except Exception:
            pass
        try:
            await system.action.disarm()
        except Exception:
            pass

    try:
        await vehicle._run_on_mavsdk_loop(_reset())
        await asyncio.sleep(2)
    except Exception:
        pass


async def _connect_and_wait_gps(vehicle_class, connection_string: str, timeout: int = SITL_GPS_TIMEOUT):
    """Connect vehicle and wait for 3D GPS fix."""
    from aerpawlib.v1.exceptions import ConnectionTimeoutError

    try:
        vehicle = await asyncio.to_thread(vehicle_class, connection_string)
    except ConnectionTimeoutError:
        pytest.fail(f"Connection timeout to {connection_string}")
    except Exception as e:
        pytest.fail(f"Vehicle init failed: {type(e).__name__}: {e}")

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        fix = vehicle.gps.fix_type
        if fix >= 3:
            return vehicle
        await asyncio.sleep(1)

    vehicle.close()
    pytest.fail(f"No 3D GPS fix within {timeout}s")


# ---------------------------------------------------------------------------
# Integration test fixtures (connected vehicles with full reset between tests)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def connected_drone(sitl_connection_string: str) -> AsyncGenerator:
    """Drone connected to SITL. Full reset before each test."""
    from aerpawlib.v1.vehicle import Drone

    drone = await _connect_and_wait_gps(Drone, sitl_connection_string)
    yield drone
    try:
        await _full_sitl_reset(drone)
    finally:
        drone.close()


@pytest_asyncio.fixture
async def connected_rover(sitl_connection_string: str) -> AsyncGenerator:
    """Rover connected to SITL. Full reset before each test."""
    from aerpawlib.v1.vehicle import Rover

    rover = await _connect_and_wait_gps(Rover, sitl_connection_string)
    yield rover
    try:
        await _full_sitl_reset(rover)
    finally:
        rover.close()
