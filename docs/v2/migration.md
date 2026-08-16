## Overview

Port an existing `aerpawlib.v1` experiment to `aerpawlib.v2`. Behavior is similar; the connect/initialize surface and a few helper names differ.

## Import and connect

```python
# v1
from aerpawlib.v1 import BasicRunner, Drone, entrypoint
vehicle = Drone("udpin://127.0.0.1:14550")  # blocking
vehicle.initialize(True)

# v2
from aerpawlib.v2 import BasicRunner, Drone, entrypoint
drone = await Drone.connect("udpin://127.0.0.1:14550")
await drone.initialize(True)
```

Prefer the CLI (`--api-version v2`); it calls `connect` and `initialize` for you.

## Commands

| v1 | v2 |
|----|----|
| `await drone.takeoff(10)` | `await drone.takeoff(altitude=10)` (positional still works) |
| `await drone.goto_coordinates(c)` | same; add `blocking=False` for a `VehicleTask` |
| `in_background(drone.goto_coordinates(c))` | `await drone.goto_coordinates(c, blocking=False)` or `in_background(...)` |
| `initialize()` is **sync** | `await initialize()` |
| Safety client on `vehicle.safety` | same fail-closed path; v2 also exposes `can_*` |

## Runners

`@entrypoint`, `@state`, `@timed_state`, `@background`, `@at_init`, `@expose_zmq`, `@expose_field_zmq` exist in both. v2 also re-exports `in_background` and `sleep`.

Multi-vehicle: `await self.wait_for_peers(["follower"])` before the first `transition_runner`.

## Other

- Plan paths: v2 `read_from_plan(Path(...))`.
- Platform class: `AERPAW_Platform` → `AerpawPlatform`.
- Exceptions: v2 errors have `code` and `severity`.
- Close: `await drone.aclose()`, not `drone.close()`.
- Mode string is `"OFFBOARD"` (ArduPilot GUIDED via MAVSDK). Compare with `vehicle.mode in ("OFFBOARD", "GUIDED")`.
