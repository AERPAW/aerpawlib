## Overview

Vehicle classes expose async commands and telemetry for experiment scripts. The CLI connects a `Drone` or `Rover` and passes it to your runner.

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
    await drone.aclose()
```

## Key concepts

### Types

| Class | Description |
|-------|-------------|
| `Vehicle` | Shared base: telemetry, arm/disarm, `goto_coordinates`, `can_*` |
| `Drone` | Multirotor: takeoff, land, RTL, heading, velocity |
| `Rover` | Ground: 2D goto, velocity (no takeoff/land/RTL) |
| `DummyVehicle` | Dry run without hardware (`--vehicle none`) |

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
| `set_velocity` | Not supported on the testbed | Not supported on the testbed |

### Validation and monitoring

- `can_takeoff`, `can_goto`, `can_land`: check whether a command is allowed (see `aerpawlib.v2.safety`)
- With a safety client attached, `takeoff` / `goto_coordinates` / `land` / `set_groundspeed` run those checks and raise if the command is not allowed
- If the vehicle link is lost, the CLI stops the mission (you do not need to call `watch_disconnect` yourself)

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
