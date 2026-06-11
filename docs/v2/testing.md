## Overview

Test doubles for v2 runner and vehicle logic without MAVSDK or hardware.

## When to use this

Import in unit tests or dry-run pipelines that exercise runner flow without a real connection.

## Common workflow

```python
from aerpawlib.v2 import MockVehicle, DummyVehicle, Coordinate

# Lightweight state for runner unit tests
mock = MockVehicle(position=Coordinate(35.727, -78.696, 0), armed=False)

# Full Vehicle interface, no I/O
dummy = await DummyVehicle.connect()
await dummy.goto_coordinates(target)  # succeeds silently
```

## Key concepts

| Class | Description |
|-------|-------------|
| `MockVehicle` | In-memory `VehicleProtocol` stand-in for control-flow tests |
| `DummyVehicle` | No-op `Vehicle` subclass; all commands succeed without MAVSDK |

Do not use these to validate MAVLink or autopilot behavior.

## See also

- `aerpawlib.v2.runner`: runner classes under test
- `aerpawlib.v2.vehicle`: real vehicle API
