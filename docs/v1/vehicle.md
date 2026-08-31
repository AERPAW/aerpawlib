## Overview

Vehicle classes translate your experiment commands into MAVSDK actions. The CLI connects a `Drone` or `Rover` and passes it to your runner.

## When to use this

Import `Drone` or `Rover` from `aerpawlib.v1.vehicle` (or `aerpawlib.v1`). Use `Drone` for multirotor flight; use `Rover` for ground experiments.

## Common workflow

```python
from aerpawlib.v1 import BasicRunner, Drone, VectorNED, entrypoint

class Mission(BasicRunner):
    @entrypoint
    async def run(self, vehicle: Drone):
        await vehicle.takeoff(10)
        await vehicle.goto_coordinates(vehicle.position + VectorNED(20, 0, 0))
        await vehicle.land()
```

> **Note:** The CLI closes the vehicle when the script ends. If you construct a vehicle yourself, call `close()` when you are done.

## Key concepts

### Commands (Drone)

| Command | Description |
|---------|-------------|
| `takeoff(altitude)` | Climb to relative altitude (m) |
| `goto_coordinates(coord, …)` | Fly to `Coordinate` |
| `set_heading(degrees, …)` | Turn to heading |
| `land()` | Land at current position |
| `return_to_launch()` | RTL and land |
| `set_velocity(VectorNED, …)` | Not supported on the AERPAW testbed (velocity commands are filtered) |

With `--safety-checker-ip` / `--safety-checker-port` (or `vehicle.safety` set), `takeoff`, `goto_coordinates`, `land`, and `set_groundspeed` ask the safety server first. A rejected maneuver raises an error and does not run. On AERPAW the default host is this node's C-VM XV (`AP_EXPENV_CVM_<n>_XV`).

### Telemetry

Read `position`, `battery`, `armed`, `heading`, and related properties during the mission. Positions use absolute lat/lon; altitude is relative to home.

### Rover differences

Rover omits copter-only commands (`takeoff`, `land`, `return_to_launch`, `set_heading`). Navigation uses 2D ground distance for arrival.

## Errors

| Exception | Action |
|-----------|--------|
| `ConnectionTimeoutError` | Check `--conn` and that SITL or hardware is running |
| `PortInUseError` | Use a unique `--mavsdk-port` per concurrent vehicle |
| `NotArmableError` | Wait for GPS/preflight; on hardware, ensure vehicle is disarmed at start |
| `TakeoffError` / `NavigationError` / `LandingError` | Inspect `message`; verify GPS fix and safety constraints |
| `NotImplementedForVehicleError` | Call movement APIs on `Drone` or `Rover`, not base `Vehicle` |

## See also

- `aerpawlib.v1.util`: `Coordinate`, `VectorNED`
- `aerpawlib.v1.safety`: geofence validation
- `aerpawlib.v2.vehicle`: v2 vehicle API
