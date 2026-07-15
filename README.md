# aerpawlib

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-1.4.5-blue)
[![Unit Tests](https://github.com/AERPAW/aerpawlib/actions/workflows/ci.yml/badge.svg)](https://github.com/AERPAW/aerpawlib/actions/workflows/ci.yml)
[![Ruff](https://github.com/AERPAW/aerpawlib/actions/workflows/ruff.yml/badge.svg)](https://github.com/AERPAW/aerpawlib/actions/workflows/ruff.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://aerpaw.github.io/aerpawlib)
[![AERPAW](https://img.shields.io/badge/platform-AERPAW-orange)](https://aerpaw.org)

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
pip install -e .
# Note that -e allows for local editing of the library (suitable for developers).
aerpawlib-setup-sitl  # This allows integration tests to work by installing and building ardupilot
```

Or use the one-liner script:

```bash
./scripts/install_dev.sh
```

This installs all dependencies, ArduPilot SITL, MAVProxy, and compiles Copter + Rover SITL.

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
> Integration tests require stdout/stderr capturing to be disabled. This is configured by default via the `-s` flag in `pytest.ini`. If running pytest manually with custom overrides, ensure `-s` (or `--capture=no`) is included.
> This is because MAVProxy will block and wait for user input when we don't need or want that behavior. Weird, seemingly unrelated errors will show up without `-s`

## Quick Start

```python
# my_mission.py
from aerpawlib.v2 import Drone, VectorNED, BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(10)
        await drone.goto_coordinates(drone.position + VectorNED(20, 0))
        await drone.land()
```

```bash
aerpawlib --script my_mission.py --conn udpin://127.0.0.1:14550 --vehicle drone
```

## Documentation

There is a GitHub pages site with documentation for this project: https://aerpaw.github.io/aerpawlib

## Examples

```bash
# Basic square flight
aerpawlib --script examples/v1/basic_example.py --conn udpin://127.0.0.1:14550 --vehicle drone

# A more complex example using --config to specify multiple arguments at once
aerpawlib --config configs/v1-drone.json --config configs/sitl-drone.json --script examples.v1.basic_runner
```

See [examples/README.md](examples/README.md) for full list.

## License

MIT License: see [LICENSE](LICENSE).
