# aerpawlib Test Suite

Pytest-based tests for aerpawlib v1 API. **SITL is managed by pytest** for integration tests: it starts ArduPilot SITL before tests and stops it after. A full SITL reset (disarm, clear mission, battery reset) runs between each integration test.

## Structure

```
tests/
├── conftest.py           # Fixtures, SITL manager, markers
├── unit/                 # Unit tests (no SITL)
│   ├── test_v1_util.py       # Coordinate, VectorNED, plan, geofence
│   ├── test_v1_helpers.py    # wait_for_condition, validate_*
│   ├── test_v1_runner.py     # BasicRunner, StateMachine
│   ├── test_v1_external.py   # ExternalProcess
│   └── test_v1_exceptions.py # Exception hierarchy
└── integration/          # Integration tests (SITL)
    ├── test_v1_drone.py     # Drone connection, takeoff, nav, land
    ├── test_v1_rover.py     # Rover (requires ArduRover SITL)
    └── test_v1_vehicles.py  # DummyVehicle (no SITL)
```

## Prerequisites

1. **Unit tests**: `pip install pytest pytest-asyncio`
2. **Integration tests**: ArduPilot SITL
   - Run `./install_ardupilot.sh` or set `ARDUPILOT_HOME` to your ArduPilot clone
   - Pytest will start `sim_vehicle.py -v ArduCopter` automatically

## Running Tests

### Unit tests only (fast, no SITL)

```bash
pytest tests/unit/ -v
# or
pytest -m unit -v
```

### Integration tests (pytest manages SITL)

```bash
pytest tests/integration/ -v
# or
pytest -m integration -v
```

Pytest will:
1. Start ArduPilot SITL on port 14550 (or `--sitl-port`)
2. Run integration tests
3. Perform full SITL reset between each test
4. Stop SITL when done

### Use external SITL (pytest does not start/stop)

```bash
# Terminal 1: start SITL manually
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550 --no-mavproxy -w

# Terminal 2: run tests
pytest tests/integration/ -v --no-sitl
```

### Options

| Option | Description |
|--------|-------------|
| `--sitl-port PORT` | UDP port for SITL (default: 14550) |
| `--no-sitl` | Do not start SITL; use externally running instance |
| `--sitl-manage` | Pytest starts/stops SITL (default: True) |

### Environment variables

- `SITL_VERBOSE=1` – show SITL stdout/stderr
- `SIM_SPEEDUP=5` – simulation speed (default: 5)
- `ARDUPILOT_HOME` – path to ArduPilot (or use `./ardupilot`)

## Markers

- `unit` – unit tests (auto-applied to `tests/unit/`)
- `integration` – integration tests (auto-applied to `tests/integration/`)
