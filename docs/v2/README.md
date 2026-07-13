> **Note:** This is the v2 API. For the backwards-compatible API, see `aerpawlib.v1`.

## Overview

The v2 API is an async-first framework for AERPAW experiment scripts. A single event loop drives your runner and vehicle commands; telemetry is available as plain attributes updated from MAVSDK.

## When to use this

- You are starting a new experiment script
- You want simpler connection strings (`udpin://127.0.0.1:14550`) and built-in `can_takeoff` / `can_goto` validation
- You prefer non-blocking `goto_coordinates(..., blocking=False)` with `VehicleTask` handles

## Quick start

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

Structured experiment logs: pass `--structured-log FILE` for JSON Lines (`mission_start`, throttled `telemetry`, `command`, `arm`/`disarm` events).

## Runners

| Runner | Use when |
|--------|----------|
| `BasicRunner` | One `@entrypoint` coroutine |
| `StateMachine` | `@state` / `@timed_state` transitions, `@background`, `@at_init` |
| `ZmqStateMachine` | Multi-vehicle remote control via ZMQ |

| Decorator | Class | Description |
|-----------|-------|-------------|
| `@entrypoint` | `BasicRunner` | Single async entry point |
| `@state(name, first=False)` | `StateMachine` | State; return next name or `None` to finish |
| `@timed_state(name, duration, …)` | `StateMachine` | State held for at least `duration` seconds |
| `@background` | `StateMachine` | Concurrent coroutine restarted on exception |
| `@at_init` | `StateMachine` | Runs once before arm and first state |
| `@expose_zmq(name)` | `ZmqStateMachine` | Remote state transition target |
| `@expose_field_zmq(name)` | `ZmqStateMachine` | Queryable field via `query_field` |

Run ZMQ missions with `--zmq-identifier` and `--zmq-proxy-server` after starting `aerpawlib-run-proxy`.

Details: `aerpawlib.v2.runner`.

## Vehicles

Connect explicitly when not using the CLI:

```python
from aerpawlib.v2.safety import SafetyCheckerClient

drone = await Drone.connect(
    "udpin://127.0.0.1:14550",
    safety=SafetyCheckerClient("127.0.0.1", 14580),
    timeout=60.0,
)
```

### Telemetry properties

| Property | Type | Description |
|----------|------|-------------|
| `position` | `Coordinate` | Lat, lon, alt AGL |
| `home_coords` | `Coordinate \| None` | Home position |
| `battery` | `Battery` | Voltage, current, remaining % |
| `gps` | `GPSInfo` | Fix type, satellite count |
| `armed` | `bool` | Armed state |
| `heading` | `float` | Degrees |
| `velocity` | `VectorNED` | m/s |
| `attitude` | `Attitude` | Roll, pitch, yaw (rad) |
| `mode` | `str` | Flight mode name |
| `connected` / `closed` | `bool` | Connection lifecycle |

### Drone commands

```python
await drone.takeoff(altitude=10)
await drone.goto_coordinates(target, tolerance=2)
await drone.set_heading(90)
await drone.land()
await drone.return_to_launch()
await drone.set_velocity(VectorNED(5, 0, 0), duration=10)
await drone.stop_velocity()
```

Non-blocking goto:

```python
handle = await drone.goto_coordinates(target, blocking=False)
await handle.wait_done()  # or handle.cancel()
```

### Rover

`Rover` shares the base interface with 2D ground tolerance (default 2.1 m). No `takeoff`, `land`, `return_to_launch`, or `set_heading`.

Details: `aerpawlib.v2.vehicle`.

## Validate before flight

```python
ok, msg = await drone.can_takeoff(10)
if not ok:
    print(msg)
    return
await drone.takeoff(altitude=10)
```

Checks include armable status, GPS fix, battery, and optional safety server rules. See `aerpawlib.v2.safety`.

## Plan files

```python
from pathlib import Path
from aerpawlib.v2.plan import read_from_plan, get_location_from_waypoint

for wp in read_from_plan(Path("mission.plan")):
    await drone.goto_coordinates(get_location_from_waypoint(wp))
```

v2 uses `pathlib.Path` for plan paths (v1 often accepts `str`).

## Supporting modules

| Module | Purpose |
|--------|---------|
| `aerpawlib.v2.types` | `Coordinate`, `VectorNED`, `Battery`, … |
| `aerpawlib.v2.plan` | QGroundControl `.plan` parsing |
| `aerpawlib.v2.geofence` | Polygon utilities |
| `aerpawlib.v2.external` | `ExternalProcess` for subprocess I/O |
| `aerpawlib.v2.testing` | `MockVehicle`, `DummyVehicle` |
| `aerpawlib.v2.exceptions` | `AerpawlibError` hierarchy |

## Error handling

Catch `AerpawlibError` subclasses (`TakeoffError`, `NavigationError`, `UnexpectedDisarmError`, …). Each exposes `message`, `code`, `severity`, and optional `original_error`.

`UnexpectedDisarmError` terminates the runner if the vehicle disarms mid-mission (e.g. failsafe).

Full hierarchy: `aerpawlib.v2.exceptions`.

## See also

- `aerpawlib.v1`: legacy API
- `aerpawlib.cli`: CLI flags and config files
