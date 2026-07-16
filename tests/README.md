# aerpawlib Test Suite

Pytest-based tests for aerpawlib v1 and v2 APIs. See the root [README.md](../README.md#running-tests) for quick-start testing; this document covers structure and contributor guidelines. SITL is managed by pytest for integration tests: it starts ArduPilot SITL before tests and stops it after. A full SITL reset (disarm, clear mission, battery reset) runs between each integration test.

## Structure

```
tests/
├── conftest.py              # Fixtures, SITL manager, markers
├── unit/                    # Unit tests (no SITL)
│   ├── test_v1_util.py          # Coordinate, VectorNED, plan, geofence
│   ├── test_v1_helpers.py       # wait_for_condition, validate_*
│   ├── test_v1_runner.py        # BasicRunner, StateMachine
│   ├── test_v1_external.py      # ExternalProcess
│   ├── test_v1_exceptions.py    # Exception hierarchy
│   ├── test_v1_safety.py        # Safety wire format
│   ├── test_v1_vehicle.py       # DummyVehicle, UDP parsing
│   ├── test_v2_types.py         # v2 Coordinate, VectorNED, etc.
│   ├── test_v2_exceptions.py    # v2 exception hierarchy
│   ├── test_v2_geofence.py      # v2 KML geofence parsing
│   ├── test_v2_runner.py        # v2 BasicRunner, StateMachine, ZMQ
│   ├── test_v2_testing.py       # MockVehicle
│   ├── test_v2_vehicle.py       # ConnectionState, DummyVehicle, aclose
│   ├── test_v2_plan.py          # v2 QGC plan parsing
│   ├── test_v2_validation.py      # PreflightChecks, can_takeoff/goto/land
│   ├── test_v2_task.py          # VehicleTask cancel/progress
│   ├── test_v2_navigation.py    # Goto polling helpers
│   ├── test_config_merge.py     # Layered --config JSON merge
│   ├── test_connection_string.py # udpin:// parsing and validation
│   ├── test_disconnect.py       # CLI disconnect racing
│   ├── test_main_runner_discovery.py
│   └── test_progress_bar.py     # Rich status bar
└── integration/             # Integration tests (SITL)
    ├── test_v1_drone.py         # v1 Drone connection, takeoff, nav, land
    ├── test_v1_rover.py         # v1 Rover (requires Rover SITL)
    ├── test_v1_vehicles.py      # v1 DummyVehicle (no SITL)
    ├── test_v2_drone.py         # v2 Drone
    ├── test_v2_rover.py         # v2 Rover
    ├── test_v2_safety.py        # v2 safety client integration
    ├── test_v2_state_machine.py # v2 StateMachine
    ├── test_v2_velocity.py      # v2 offboard velocity
    └── test_v2_vehicle_task_cancel.py
```

## Prerequisites

1. Unit tests: `pip install -e .`
1. Integration tests: `pip install -e .` then run `aerpawlib-setup-sitl` (or `./scripts/install_dev.sh`) to install the modified ArduPilot SITL. Pytest then starts ArduCopter SITL for drone tests and ArduRover SITL for rover tests (separate ports).

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

1. Start ArduCopter SITL with MAVProxy on instance 0, UDP output to port 14550
1. Start Rover SITL with MAVProxy on instance 1, UDP output to port 14560
1. Run integration tests (only starts SITLs for the vehicle types being tested)
1. Perform full SITL reset between each test
1. Stop SITL when done

Different instance IDs (`-I 0` for drone, `-I 1` for rover) ensure the internal TCP ports don't conflict when running both concurrently.

### Use external SITL (pytest does not start/stop)

```bash
# Terminal 1: start drone SITL (instance 0)
sim_vehicle.py -v ArduCopter -I 0 --out=udp:127.0.0.1:14550 -w

# Terminal 2: start rover SITL (instance 1, different internal ports)
sim_vehicle.py -v Rover -I 1 --out=udp:127.0.0.1:14560 -w

# Terminal 3: run tests
pytest tests/integration/ -v --no-sitl
```

### Options

| Option | Description |
|--------------------------|-----------------------------------------------------------------------------------|
| `--instance INSTANCE` | Legacy: SITL instance ID for drone (default: 0) |
| `--instance-drone INSTANCE`| SITL instance ID for ArduCopter SITL (default: 0) |
| `--instance-rover INSTANCE`| SITL instance ID for ArduRover SITL (default: 1) |
| `--no-sitl` | Do not start SITL; use externally running instance |

### Log files

SITL output is captured to separate log files per vehicle type:

- `logs/sitl_drone_output.log`: sim_vehicle.py output (build, progress)
- `logs/sitl_rover_output.log`: sim_vehicle.py output (build, progress)
- `logs/sitl_drone_process.log`: ArduCopter SITL binary output (headless process log)
- `logs/sitl_rover_process.log`: Rover SITL binary output (headless process log)

Pytest redirects ArduPilot's default `/tmp/<Vehicle>.log` output to the repo-local `logs/` files above so all test logs are stored together.

Pytest unsets `DISPLAY` so sim_vehicle does not open a new Terminal window; the SITL process runs headless.

Integration tests disable pytest output capture (`-s` behavior) because MAVProxy blocks when stdout is a pipe.

### Environment variables

- `SITL_VERBOSE=1`: show SITL stdout/stderr
- `SIM_SPEEDUP=5`: simulation speed (default: 5)
- `ARDUPILOT_HOME`: path to ArduPilot (or use `./ardupilot`)

## Markers

- `unit`: unit tests (auto-applied to `tests/unit/`)
- `integration`: integration tests (auto-applied to `tests/integration/`)

## Troubleshooting

### "Mode change to GUIDED failed: requires position"

This occurs when starting an experiment before SITL has fully initialized. MAVSDK can briefly report the vehicle as ready before position data is actually usable.

Solutions:

- Wait for SITL to fully start: Give SITL 10 to 15 seconds after `sim_vehicle.py` reports "Ready to FLY" before running your script.
- Use external SITL: Run SITL in a separate terminal first, then run your experiment with `--no-sitl` (for pytest) after SITL is ready.

v2 integration fixtures wait for a 3D GPS fix and EKF readiness before yielding the connected vehicle.
