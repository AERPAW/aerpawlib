# aerpawlib Test Suite

Pytest-based tests for aerpawlib v1 and v2 APIs. See the root [README.md](../README.md#running-tests) for quick-start testing; this document covers structure and contributor guidelines. SITL is managed by pytest for integration tests: it starts ArduPilot SITL before tests and stops it after. A full SITL reset (disarm, clear mission, battery reset) runs between each integration test.

## Structure

```
tests/
├── conftest.py       # Fixtures, SITL manager, markers
├── unit/             # Unit tests (no SITL)
└── integration/      # Integration tests (SITL)
```

## Prerequisites

1. Unit tests: `pip install -e ".[dev]"`
1. Integration tests: `pip install -e ".[dev,sitl]"` then run `aerpawlib-setup-sitl` (or `./scripts/install_dev.sh`) to install ArduPilot SITL. Pytest then starts ArduCopter SITL for drone tests and ArduRover SITL for rover tests (separate ports).

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

SITL output is captured per vehicle type:

- `logs/sitl_drone_output.log`: sim_vehicle.py output (build, progress)
- `logs/sitl_rover_output.log`: sim_vehicle.py output (build, progress)
- `/tmp/ArduCopter.log`: ArduCopter SITL binary log
- `/tmp/Rover.log`: Rover SITL binary log

Pytest unsets `DISPLAY` so sim_vehicle does not open a new Terminal window; the SITL process runs headless.

Integration tests disable pytest output capture (`-s` behavior) because MAVProxy blocks when stdout is a pipe.

### Environment variables

- `SITL_VERBOSE=1`: show SITL stdout/stderr
- `SIM_SPEEDUP=2`: simulation speed (default: 2)
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
