## Overview

Vehicle API for v1 experiments.

This module provides concrete v1 vehicle types and compatibility wrappers so
scripts can use one import surface for vehicle interactions.

High-level overview
-------------------
- `Vehicle`
  - Shared MAVSDK-backed base class used by v1 vehicle implementations.
  - Owns connection lifecycle, telemetry synchronization, and command bridging
    to the background MAVSDK event loop.

- `Drone`
  - Multirotor implementation with takeoff/land/RTL, goto helpers, heading
    control, and velocity control.

- `Rover`
  - Ground vehicle implementation focused on 2D navigation and rover-specific
    mode handling.

- `DummyVehicle`
  - Test/compatibility vehicle used by simulation or no-op flows.


## Runtime model

v1 vehicles use a two-loop architecture:

- User runner code executes on the main asyncio loop.
- MAVSDK operations execute on a dedicated background thread with its own
  event loop.
- Vehicle methods bridge loops via internal helpers and thread-safe state
  wrappers.
- Telemetry streams update thread-safe values that power sync-style properties
  (`position`, `armed`, `battery`, etc.).

## Usage

```python
from aerpawlib.v1 import BasicRunner, Drone, entrypoint

class Mission(BasicRunner):
    @entrypoint
    async def run(self, vehicle: Drone):
        await vehicle.takeoff(10)
        await vehicle.goto_coordinates(vehicle.position)
        await vehicle.land()

# Vehicle objects are created by the CLI runner; call close() on shutdown.
```

## Errors

Connection/setup (mostly from `Vehicle` base):

- `ConnectionTimeoutError`: no connection established within configured timeout.
- `AerpawConnectionError`: MAVSDK transport/grpc/connectivity failures.
- `PortInUseError`: requested MAVSDK server port is already bound.
- `NotArmableError`: preflight checks fail or vehicle starts already armed.

Command-level failures:

- `ArmError`, `DisarmError`: arming state transitions fail.
- `TakeoffError`, `LandingError`, `RTLError`: multirotor action failures.
- `NavigationError`: goto/action timeouts or command failures.
- `VelocityError`: set-velocity/offboard command failures.

API contract errors:

- `NotImplementedForVehicleError`: calling movement APIs on base `Vehicle`
  instead of a concrete type.
- Some low-level loop-bridge failures can surface as `RuntimeError` when the
  MAVSDK loop is unavailable during shutdown/race conditions.

## Implementation notes

- `Vehicle.__init__` connects synchronously and starts internal telemetry/
  command machinery before returning.
- `Drone` waits for initial armed-state telemetry and rejects startup when the
  vehicle is already armed.
- `Rover` performs GUIDED-mode setup via direct MAVLink command before arming.
- Blocking movement methods update `_ready_to_move` predicates and wait until
  position/heading conditions are met.
- `close()` cancels pending futures/tasks and stops background loop resources;
  skipping it can leave lingering threads/sockets.

## Notes

- Prefer high-level APIs like `goto_coordinates(...)`, `set_velocity(...)`, and
  `set_heading(...)` over direct MAVSDK calls.
- Wrap mission commands in try/except for `AerpawlibError` subclasses when you
  need explicit recovery behavior.
