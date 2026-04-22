## Overview

v2 provides command validation (`can_takeoff`, `can_goto`, `can_land`) with optional integration to an external SafetyCheckerServer via `vehicle.safety`. Enforcement stays in the autopilot and C-VM (Controller VM) on AERPAW.

## Command Validation

Before running a command, check if it would succeed:

```python
ok, msg = await drone.can_takeoff(10)
if not ok:
    print(f"Cannot takeoff: {msg}")
    return
await drone.takeoff(altitude=10)
```

### can_takeoff

Local checks: armable, GPS 3D fix, minimum battery. If `vehicle.safety` is set, also calls `safety.validate_takeoff`.

### can_goto

Local checks: tolerance within valid range. If `vehicle.safety` is set, calls `safety.validate_waypoint`.

### can_land

If `vehicle.safety` is set, calls `safety.validate_landing`. Otherwise returns `(True, "")`.

## vehicle.safety

The vehicle constructor and `connect()` accept a `safety` argument (a `SafetyCheckerClient` or `NoOpSafetyChecker`). Pass it when connecting:

```python
from aerpawlib.v2.safety import SafetyCheckerClient

client = SafetyCheckerClient("127.0.0.1", 14580)
drone = await Drone.connect("udpin://127.0.0.1:14550", safety=client)
ok, msg = await drone.can_takeoff(10)
```

You can also set `vehicle.safety` after construction if needed. If `safety` is `None`, `can_*` methods run only local checks (for takeoff/goto) or return success (for land).

### Automatic Setup via CLI (`--safety-checker-port`)

When you run aerpawlib v2 via the CLI, a safety client (real or passthrough) is built first and passed to `vehicle.connect(safety=...)`. The vehicle constructor is responsible for accepting and storing the safety client.

| Environment | `--safety-checker-port`                       | Behavior                                                                                                                               |
|-------------|-----------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| Non-AERPAW  | Not provided                                  | `vehicle.safety` uses a passthrough checker: all validations pass, errors logged explaining the SafetyCheckerServer is not configured. |
| Non-AERPAW  | Provided (e.g. `--safety-checker-port 14580`) | Attempts to connect to `127.0.0.1:<port>`. On failure: uses passthrough, logs the error.                                               |
| AERPAW      | Not provided                                  | Defaults to port 14580. Attempts to connect. **On failure: crash with critical error.**                                                |
| AERPAW      | Provided                                      | Attempts to connect to given port. **On failure: crash with critical error.**                                                          |

The passthrough checker (`NoOpSafetyChecker`) always returns success for all validations but logs that the SafetyCheckerServer is not available. Use it only for local development when no geofence server is running.

```bash
# Non-AERPAW: optional, uses passthrough if not provided or connection fails
aerpawlib --api-version v2 --script my_mission.py --vehicle drone --conn ... --safety-checker-port 14580

# AERPAW: defaults to 14580; must succeed or program exits
aerpawlib --api-version v2 --script my_mission.py --vehicle drone --conn ...
```

## SafetyCheckerClient

Async ZMQ client for external geofence validation:

```python
from aerpawlib.v2.safety import SafetyCheckerClient

client = SafetyCheckerClient(addr="192.168.32.25", port=14580)
ok, msg = await client.validate_waypoint(current, next_loc)
ok, msg = await client.validate_takeoff(altitude, lat, lon)
ok, msg = await client.validate_landing(lat, lon)
```

## PreflightChecks

Integrated preflight checks before arm/takeoff:

```python
from aerpawlib.v2.safety import PreflightChecks

ok = await PreflightChecks.run_all(vehicle)
# Checks: GPS 3D fix, minimum battery
```

## ConnectionHandler

Single authority for connection state and heartbeat.

- Starts monitoring after first telemetry or short delay.
- On disconnect: notify OEO, trigger callbacks, exit.
- Uses `loop.add_signal_handler()` for async-safe SIGINT/SIGTERM where available.
