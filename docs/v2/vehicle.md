## Overview

Vehicle classes connect to ArduPilot via MAVSDK and expose async commands and telemetry for experiment scripts. The CLI constructs and passes a `Drone` or `Rover` to your runner.

## When to use this

Import from `aerpawlib.v2.vehicle` (or `aerpawlib.v2`). Use `DummyVehicle` for dry runs without hardware.

## Common workflow

```python
from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint

class Mission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=10)
        await drone.goto_coordinates(drone.position + VectorNED(20, 0))
        await drone.land()
```

Manual connection:

```python
drone = await Drone.connect("udpin://127.0.0.1:14550")
try:
    await drone.takeoff(altitude=10)
finally:
    drone.close()
```

## Key concepts

### Types

| Class | Description |
|-------|-------------|
| `Vehicle` | Shared base: telemetry, arm/disarm, `goto_coordinates`, `can_*` |
| `Drone` | Multirotor: takeoff, land, RTL, heading, velocity |
| `Rover` | Ground: 2D goto, velocity (no takeoff/land/RTL) |
| `DummyVehicle` | No-op for pipeline tests |

### Telemetry

`position`, `home_coords`, `battery`, `gps`, `armed`, `heading`, `velocity`, `attitude`, `mode`, `connected`, `closed`: read as normal attributes.

### Commands

All commands are `async`. `goto_coordinates` blocks by default; pass `blocking=False` for a `VehicleTask` handle (`progress`, `cancel()`, `wait_done()`).

| Command | Drone | Rover |
|---------|-------|-------|
| `takeoff` | Yes | - |
| `goto_coordinates` | 3D tolerance (default 2 m) | 2D tolerance (default 2.1 m) |
| `land` / `return_to_launch` | Yes | - |
| `set_heading` | Yes | - |
| `set_velocity` | Full NED | `down` ignored |

### Validation and monitoring

- `can_takeoff`, `can_goto`, `can_land`: preflight checks (see `aerpawlib.v2.safety`)
- `watch_disconnect(timeout)`: future completes on heartbeat loss (CLI handles this automatically)

## Errors

| Exception | Action |
|-----------|--------|
| `ConnectionTimeoutError` | Verify connection string and vehicle process |
| `HeartbeatLostError` | Link lost mid-mission; runner may terminate |
| `NotArmableError` / `NotConnectedError` | Wait for ready state before commands |
| `TakeoffError` / `NavigationError` | Check GPS, battery, safety server response |
| `UnexpectedDisarmError` | Failsafe or manual disarm during mission |

## See also

- `aerpawlib.v2.types`: `Coordinate`, `VectorNED`
- `aerpawlib.v2.safety`: safety client integration
- `aerpawlib.v1.vehicle`: v1 vehicle API
