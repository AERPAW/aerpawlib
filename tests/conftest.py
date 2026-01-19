"""
Pytest configuration and shared fixtures for aerpawlib tests.
"""

import pytest
import asyncio
import sys
import os

# Ensure the project root is in the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# ============================================================================
# Event Loop Configuration
# ============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ============================================================================
# Coordinate and Vector Fixtures
# ============================================================================


@pytest.fixture
def origin_coordinate():
    """A coordinate at AERPAW Lake Wheeler site."""
    from aerpawlib.v1.util import Coordinate

    return Coordinate(35.727436, -78.696587, 0)


@pytest.fixture
def nearby_coordinate():
    """A coordinate ~100m north of origin."""
    from aerpawlib.v1.util import Coordinate

    return Coordinate(35.728336, -78.696587, 0)


@pytest.fixture
def sample_vector():
    """A sample VectorNED for testing."""
    from aerpawlib.v1.util import VectorNED

    return VectorNED(100.0, 50.0, -10.0)


@pytest.fixture
def zero_vector():
    """A zero VectorNED."""
    from aerpawlib.v1.util import VectorNED

    return VectorNED(0, 0, 0)


@pytest.fixture
def unit_north_vector():
    """A unit vector pointing north."""
    from aerpawlib.v1.util import VectorNED

    return VectorNED(1, 0, 0)


# ============================================================================
# SITL Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def sitl_connection_string():
    """Get the SITL connection string."""
    return "udp:127.0.0.1:14551"


@pytest.fixture
async def connected_drone(sitl_connection_string):
    """
    Provide a connected Drone instance for testing.

    The drone is connected to SITL and ready for commands.
    """
    from aerpawlib.v1.vehicle import Drone

    drone = Drone(sitl_connection_string)

    # Wait for GPS fix
    timeout = 60
    import time

    start = time.time()
    while drone.gps.fix_type < 3 and (time.time() - start) < timeout:
        await asyncio.sleep(0.5)

    yield drone

    # Cleanup: disarm if armed, close connection
    if drone.armed:
        try:
            await drone._run_on_mavsdk_loop(drone._system.action.disarm())
        except Exception:
            pass
    drone.close()


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (no external dependencies)"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (requires SITL)",
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """Auto-add markers based on test location."""
    for item in items:
        # Add 'unit' marker to tests in unit/ directory
        if "/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Add 'integration' marker to tests in integration/ directory
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
