## Overview

`aerpawlib` is a high-level Python library for controlling autonomous vehicles on the [AERPAW testbed](https://aerpaw.org). Write experiment scripts that focus on mobility and wireless research; the library handles MAVSDK and ArduPilot communication.

## When to use this

Use `aerpawlib` when you run scripted experiments on AERPAW drones or rovers. Install the package (see the [repository README](https://github.com/AERPAW/aerpawlib/blob/main/README.md)), define a **runner** class, and launch it with the `aerpawlib` CLI.

## Choosing an API version

| Version | Module | Best for |
|---------|--------|----------|
| **v2** (recommended for new work) | `aerpawlib.v2` | New experiments; single asyncio loop, simpler connection strings (`udpin://…`), built-in safety hooks |
| **v1** (stable, legacy-compatible) | `aerpawlib.v1` | Existing scripts written for the original aerpawlib API; full multi-vehicle and feature parity |

> **Note:** Imports from `aerpawlib` (without `.v1`) still work but are deprecated in favor of `aerpawlib.v1`.

## Documentation index

| Module | Description |
|--------|-------------|
| `aerpawlib.v2` | v2 API overview and quick reference |
| `aerpawlib.v1` | v1 API overview and getting started |
| `aerpawlib.cli` | CLI flags, config files, and execution flow |
| `aerpawlib.log` | Logging and structured JSONL output |

## Common workflow

```python
from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint

class MyExperiment(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=10)
        await drone.goto_coordinates(drone.position + VectorNED(20, 0))
        await drone.land()
```

```bash
aerpawlib --api-version v2 --script my_experiment.py --vehicle drone --conn udpin://127.0.0.1:14550
```

## See also

- [docs/DOC_STYLE.md](DOC_STYLE.md): documentation conventions for contributors
- `examples/`: runnable mission scripts for v1 and v2
