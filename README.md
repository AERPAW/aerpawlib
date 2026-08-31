# aerpawlib

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-1.4.9-blue)
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

## Installation

```bash
pip install .
```

On AERPAW C-VMs the library is already available. For a local simulator, install SITL extras and build ArduPilot:

```bash
pip install -e ".[sitl]"
aerpawlib-setup-sitl
```

## Quick Start

```python
# my_mission.py
from aerpawlib.v2 import Drone, VectorNED, BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=25)
        await drone.goto_coordinates(drone.position + VectorNED(20, 0))
        await drone.land()
```

```bash
aerpawlib --api-version v2 --script my_mission.py --conn udpin://127.0.0.1:14550 --vehicle drone --no-aerpaw-environment
```

`--no-aerpaw-environment` is required outside the AERPAW testbed. Copter takeoff on the testbed must be at least 20 m (examples use 25 m).

## Documentation

API reference for writing experiment scripts: https://aerpaw.github.io/aerpawlib

## Examples

```bash
# Basic square flight
aerpawlib --script examples/v1/basic_example.py --conn udpin://127.0.0.1:14550 --vehicle drone --no-aerpaw-environment

# A more complex example using --config to specify multiple arguments at once
aerpawlib --config configs/v1-drone.json --config configs/sitl-drone.json --script examples.v1.basic_runner
```

See [examples/README.md](examples/README.md) for the full list, including multi-vehicle ZMQ missions (`aerpawlib-run-proxy` plus `--zmq-identifier` / `--zmq-proxy-server`).

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/unit/ -v
```

Integration tests need SITL:

```bash
pip install -e ".[dev,sitl]"
aerpawlib-setup-sitl
pytest tests/integration/ -v
```

See [tests/README.md](tests/README.md) for details.

## License

MIT License: see [LICENSE](LICENSE).
