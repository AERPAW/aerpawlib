# aerpawlib Test Suite

This directory contains the test suite for aerpawlib, covering both v1 and v2 APIs.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and pytest configuration
├── unit/                    # Unit tests (no external dependencies)
│   ├── test_vector_ned.py       # v1 VectorNED tests
│   ├── test_coordinate.py       # v1 Coordinate tests
│   ├── test_runner.py           # v1 Runner/StateMachine tests
│   ├── test_util.py             # v1 utility function tests
│   ├── test_v2_vector_ned.py    # v2 VectorNED tests
│   ├── test_v2_coordinate.py    # v2 Coordinate tests
│   └── test_v2_runner.py        # v2 Runner tests
└── integration/             # SITL integration tests
    ├── test_drone_sitl.py       # v1 drone operations
    ├── test_missions.py         # v1 mission scenarios
    ├── test_sitl_manager.py     # SITL manager tests
    └── test_v2_drone_sitl.py    # v2 drone operations
```

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-timeout

# For integration tests, install ArduPilot SITL
./install_ardupilot.sh
```

### Run All Tests

```bash
pytest
```

### Run Only Unit Tests (Fast, No SITL Required)

```bash
pytest tests/unit/
# or
pytest -m unit
```

### Run Only Integration Tests (Requires SITL)

```bash
pytest tests/integration/
# or
pytest -m integration
```

### Run Specific Test File

```bash
pytest tests/unit/test_coordinate.py
```

### Run Specific Test

```bash
pytest tests/unit/test_coordinate.py::TestCoordinateDistance::test_distance_same_point
```

### Verbose Output

```bash
pytest -v
```

### Show Print Statements

```bash
pytest -s
```

### Run With Coverage

```bash
pip install pytest-cov
pytest --cov=aerpawlib --cov-report=html
# Open htmlcov/index.html in browser
```

## Test Markers

- `@pytest.mark.unit` - Unit tests (auto-applied to tests in `unit/`)
- `@pytest.mark.integration` - Integration tests (auto-applied to tests in `integration/`)
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.asyncio` - Async tests

### Skip Slow Tests

```bash
pytest -m "not slow"
```

## Environment Variables

- `SITL_VERBOSE=1` - Show SITL stdout/stderr output
- `SITL_SPEEDUP=10` - Simulation speedup factor (default: 5)

## Writing Tests

### Unit Tests

Unit tests should not require any external dependencies (SITL, network, etc.):

```python
# tests/unit/test_example.py
import pytest
from aerpawlib.v1.util import Coordinate

class TestExample:
    def test_something(self):
        coord = Coordinate(35.0, -78.0, 100)
        assert coord.alt == 100
```

### Integration Tests

Integration tests use SITL fixtures from `conftest.py`:

```python
# tests/integration/test_example.py
import pytest

pytestmark = pytest.mark.integration

class TestDroneExample:
    @pytest.mark.asyncio
    async def test_drone_operation(self, connected_drone):
        # connected_drone is already connected to SITL
        assert connected_drone.connected
        
        await connected_drone.takeoff(10)
        assert connected_drone.position.alt > 8
        
        await connected_drone.land()
```

### Available Fixtures

From `conftest.py`:

- `origin_coordinate` - Coordinate at AERPAW Lake Wheeler
- `nearby_coordinate` - Coordinate ~100m north of origin
- `sample_vector` - VectorNED(100, 50, -10)
- `zero_vector` - VectorNED(0, 0, 0)
- `unit_north_vector` - VectorNED(1, 0, 0)
- `sitl_manager` - Running SITL instance (module scope)
- `sitl_connection_string` - Connection string for SITL
- `connected_drone` - Drone connected to SITL, ready for commands

## Troubleshooting

### Tests Hang

If integration tests hang, SITL might not be starting properly:

```bash
# Run with SITL verbose output
SITL_VERBOSE=1 pytest tests/integration/test_drone_sitl.py::TestDroneConnection -v
```

### SITL Not Found

Ensure ArduPilot is installed:

```bash
./install_ardupilot.sh
# or
export ARDUPILOT_HOME=/path/to/ardupilot
```

### Async Test Issues

Make sure you have pytest-asyncio installed and tests are marked:

```python
@pytest.mark.asyncio
async def test_async_operation(self):
    await some_async_function()
```

### Timeout Issues

Increase timeout in `pytest.ini` or per-test:

```python
@pytest.mark.timeout(600)  # 10 minutes
async def test_long_running(self):
    ...
```
