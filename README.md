# aerpawlib

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![Unit Tests](https://github.com/AERPAW/aerpawlib/actions/workflows/ci.yml/badge.svg)](https://github.com/AERPAW/aerpawlib/actions/workflows/ci.yml)

A Python library for controlling vehicles within the [AERPAW](https://aerpaw.org) platform. Provides a unified interface for vehicle control, telemetry, and mission execution with ArduPilot.

## Features

- Unified vehicle control
- Scriptable missions
- Multi-vehicle coordination
- Safety checker
- AERPAW Platform integration

# Docs

See the Github Pages documentation [here](https://aerpaw.github.io/aerpawlib)

## Installation

```bash
pip install .
```

### Development (with ArduPilot SITL)

For running integration tests and local SITL simulation:

```bash
pip install -e .[dev]
# Note that -e allows for local editing of the library (suitable for developers).
aerpawlib-setup-sitl
```

Or use the one-liner script:

```bash
./scripts/install_dev.sh
```
This installs dev dependencies (pytest, etc.), ArduPilot SITL, MAVProxy, and compiles Copter + Rover SITL.

## Running Tests

The test suite consists of both unit tests and integration tests.

### Unit Tests (Fast, no SITL)
To run only the unit tests:
```bash
pytest tests/unit
```

### Integration Tests (Pytest manages SITL)
To run the integration tests (which automatically spin up and tear down ArduPilot SITL and MAVSDK server):
```bash
pytest tests/integration
```

> [!IMPORTANT]
> Integration tests require stdout/stderr capturing to be disabled so MAVProxy does not block. This is configured by default via the `-s` flag in `pytest.ini`. If running pytest manually with custom overrides, ensure `-s` (or `--capture=no`) is included.
> This is a really weird bug with how MavProxy works, just don't touch it.
## Quick Start

```python
# my_mission.py
from aerpawlib.v1 import Drone, Coordinate, BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, vehicle):
        await vehicle.takeoff(10)
        for wp in [Coordinate(35.7275, -78.6960, 10), Coordinate(35.7280, -78.6955, 10)]:
            await vehicle.goto_coordinates(wp)
        await vehicle.land()
```

```bash
aerpawlib --script my_mission.py --conn udpin://127.0.0.1:14550 --vehicle drone
```

## Documentation

There is a GitHub pages site with documentation for this project: https://aerpaw.github.io/aerpawlib

## Examples

```bash
# Basic square flight
aerpawlib --script examples/v1/basic_example.py --conn udp://127.0.0.1:14550 --vehicle drone

# Layered config presets (API/vehicle, SITL connection, optional JSONL logging)
aerpawlib --config configs/v1-drone.json --config configs/sitl-drone.json --script examples.v1.basic_runner
```

See [examples/README.md](examples/README.md) for full list.

## License

MIT License – see [LICENSE](LICENSE).
