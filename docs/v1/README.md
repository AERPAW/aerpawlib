> **Note:** This is the v1 API, intended to be backwards compatible with the old dronekit-based aerpawlib. If you are looking for the v2 API, see `aerpawlib.v2`.

## Overview

The v1 API provides a Python framework for AERPAW experiment scripts. It abstracts MAVSDK so you can express mission logic (takeoff, navigation, measurements, landing) without managing low-level flight control.

v1 matches the API of the [original aerpawlib](https://github.com/morzack/aerpawlib-vehicle-control) (DroneKit-based) but uses MAVSDK internally. There are a few minor changes though, see the **Migration from DroneKit aerpawlib** section for more information.

## When to use this

- You maintain an existing v1 experiment script
- You need multi-vehicle (ZMQ) patterns from the original DroneKit-era library
- You import from `aerpawlib.v1` (or legacy `aerpawlib.*`)

Install the package with `pip install -e .` (see the [repository README](../../README.md)).

## Tutorial: Writing your first v1 mission

This tutorial guides you through writing a basic autonomous flight mission using the backwards-compatible `v1` API.

### Step 1: Create the script

Create a file named `square_mission.py` containing a `BasicRunner` subclass. When the script runs, it will execute the `@entrypoint` method, also passing in the connected vehicle instance:

```python
import asyncio

from aerpawlib.v1 import BasicRunner, Drone, VectorNED, entrypoint

class SquareMission(BasicRunner):
    @entrypoint
    async def run(self, vehicle: Drone):
        # 1. Takeoff to 5 meters altitude
        await vehicle.takeoff(5)

        # 2. Fly a square pattern of 10m x 10m
        for north, east in [(10, 0), (0, -10), (-10, 0), (0, 10)]:
            # Add offset to current position using VectorNED
            target_pos = vehicle.position + VectorNED(north, east, 0)
            await vehicle.goto_coordinates(target_pos)
            await asyncio.sleep(5)

        # 3. Land the vehicle
        await vehicle.land()
```

### Step 2: Run in SITL

Start your ArduPilot simulation, then execute the script with the CLI:

```bash
aerpawlib --api-version v1 --script square_mission.py --vehicle drone --conn udp:127.0.0.1:14550
```

> **Note:** v1 connection strings often use `udp:`; v2 prefers `udpin://`. Match the format to your SITL or hardware setup.

## Runners

Every v1 script implements a runner, a class the CLI discovers and executes.

| Runner | Use when |
|--------|----------|
| `BasicRunner` | One linear flow; single `@entrypoint` |
| `StateMachine` | Named states with transitions (`@state`, `@timed_state`, `@background`) |
| `ZmqStateMachine` | Multi-vehicle coordination over a ZMQ proxy |

Decorator reference and error handling: see `aerpawlib.v1.runner`.

```python
from aerpawlib.v1 import StateMachine, Vehicle, state, timed_state

class MeasureMission(StateMachine):
    @state(name="start", first=True)
    async def start(self, vehicle: Vehicle):
        await vehicle.takeoff(5)
        return "patrol"

    @timed_state(name="patrol", duration=10)
    async def patrol(self, vehicle: Vehicle):
        return "land"

    @state(name="land")
    async def land(self, vehicle: Vehicle):
        await vehicle.land()
```

## Vehicles and coordinates

The CLI passes a connected `Drone` or `Rover` to your runner. Call `takeoff` explicitly at the start of drone missions.

Positions use absolute latitude and longitude. Altitude is relative to the vehicle home position. Wrap coordinates in `Coordinate`; combine with `VectorNED` for offsets.

```python
from aerpawlib.v1 import Coordinate, VectorNED

home = Coordinate(35.771634, -78.674109, 0)
north_10m = home + VectorNED(10, 0, 0)
bearing = home.bearing(north_10m)  # degrees
```

Vehicle commands and telemetry: see `aerpawlib.v1.vehicle`.

## Async essentials

Runner methods are `async`. Use `await` on vehicle commands to wait for completion, or `asyncio.ensure_future` to run movement concurrently with other work.

```python
import asyncio

# Wait for arrival
await vehicle.goto_coordinates(target)

# Start movement, do other work, then wait
move = asyncio.ensure_future(vehicle.goto_coordinates(target))
# ... collect samples ...
await move
```

Use `asyncio.sleep`, not `time.sleep`, inside runner coroutines. Background telemetry logging uses `@background` on `StateMachine` only.

## Multi-vehicle experiments

Coordinate multiple vehicles with `ZmqStateMachine`:

1. Start the proxy: `aerpawlib-run-proxy`
1. Run one ground coordinator script with high-level experiment logic
1. Run vehicle scripts with low-level commands (goto waypoint, orbit, return)

Design pattern:

- Vehicle scripts expose a idle `wait_loop` state and command states triggered remotely
- Ground script calls `transition_runner` and `query_field` on peer identifiers
- Expose data with `@expose_field_zmq`; expose command states with `@expose_zmq`

Full example: `examples/zmq_preplanned_orbit/` (tracer, orbiter, ground coordinator).

## Migration from DroneKit aerpawlib (morzack/aerpawlib-vehicle-control)

When migrating legacy scripts written for the original DroneKit-based aerpawlib, please note the following breaking changes and updates:

- The underlying `._vehicle` attribute (which exposed the raw `dronekit.Vehicle` object) is no longer available since the library backend was migrated to MAVSDK. Any script accessing `._vehicle` directly for customized telemetry or command logic must be updated to use the standard async methods provided by `aerpawlib.v1`.
- All flight commands (`takeoff`, `goto_coordinates`, `land`, `set_heading`, etc.) are now asynchronous coroutines and must be `await`ed inside your `@entrypoint` or `@state` methods. All other arguments and behavior is identical.
- MAVSDK connection syntax differs from DroneKit.

## Key modules

| Module | Purpose |
|--------|---------|
| `aerpawlib.v1.runner` | Runners and decorators |
| `aerpawlib.v1.vehicle` | `Drone`, `Rover`, movement commands |
| `aerpawlib.v1.util` | `Coordinate`, `VectorNED`, plan I/O |
| `aerpawlib.v1.safety` | Safety checker client/server |
