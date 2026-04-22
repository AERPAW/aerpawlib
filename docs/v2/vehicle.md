## Overview

The vehicle layer is how your mission code talks to hardware. v2 is built around a single asyncio loop: MAVSDK work is `await`ed, telemetry is plain attributes updated from tasks, and commands return `VehicleTask` handles when you opt into non-blocking movement.

`Drone` and `Rover` are the concrete types you will see from the CLI. `Vehicle` is the shared base (arming, `goto_coordinates`, telemetry, `can_*` validation, `connect`, `close`). `DummyVehicle` is a no-op `Vehicle` subclass for dry-runs and CI: `connect` succeeds without a real link, and movement calls complete without I/O.

### What you will use most
- Connect `await Drone.connect("udpin://...")` or `Rover.connect(...)` with optional `safety=`, `timeout=`, and structured log hooks from the runtime.
- Commands `takeoff`, `land`, `goto_coordinates`, `set_velocity`, `set_groundspeed`, `return_to_launch` (copter), `set_heading` (copter), etc. All are async; blocking is the default for goto unless you pass `blocking=False`.
- Tasks `VehicleTask` exposes `progress`, `cancel()`, `wait_done()`, and `is_done()` for long moves you want to run concurrently with other coroutines, data collection, or anything else.
- State `position`, `home_coords`, `battery`, `gps`, `armed`, `heading`, `velocity`, `attitude`, `mode`, and connection flags. Read them like normal Python fields; the implementation keeps them fresh from MAVSDK.
- Safety `can_takeoff`, `can_goto`, and `can_land` delegate to local checks and, when configured, the safety client.

### Behavior notes
- `Rover` does not expose copter-only commands (`takeoff`, `land`, `return_to_launch`, `set_heading`, and copter `stop_velocity` behavior differ); 2D tolerance and velocity semantics are documented in the top-level v2 README.
- Always `close()` when you manage a connection manually; the CLI does this for you on shutdown.
