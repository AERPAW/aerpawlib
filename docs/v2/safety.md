## Overview

Validate commands before flight and integrate with the AERPAW SafetyCheckerServer. Vehicles expose `can_takeoff`, `can_goto`, and `can_land`; pass a `SafetyCheckerClient` at connect time or set `vehicle.safety`.

## When to use this

- Preflight checks in experiment scripts before takeoff or goto
- Geofence enforcement on the AERPAW testbed (server required)
- Local development with optional passthrough when no server runs

## Common workflow

```python
from aerpawlib.v2 import Drone
from aerpawlib.v2.safety import SafetyCheckerClient

client = SafetyCheckerClient("127.0.0.1", 14580)
drone = await Drone.connect("udpin://127.0.0.1:14550", safety=client)

ok, msg = await drone.can_takeoff(10)
if not ok:
    print(msg)
    return
await drone.takeoff(altitude=10)
```

Or rely on the CLI: `--safety-checker-port` (and `--safety-checker-ip`) wire the client automatically.

## Key concepts

### can\_\* methods

| Method | Local checks | With safety client |
|--------|--------------|-------------------|
| `can_takeoff(altitude)` | Armable, GPS 3D fix, battery | + server takeoff validation |
| `can_goto(target, …)` | Tolerance bounds | + waypoint validation |
| `can_land()` | - | Server landing validation if configured |

### CLI safety behavior

| Environment | Port omitted | Port provided |
|-------------|--------------|---------------|
| Non-AERPAW | Passthrough (all checks pass, warning logged) | Connect or fall back to passthrough |
| AERPAW | Default 14580; failure exits | Connect or exit |

### SafetyCheckerClient

Asynchronous ZMQ client for direct validation. Unlike the v1 counterpart, the v2 safety client runs completely asynchronously on the shared event loop using `zmq.asyncio`. Additionally, there is no built-in `SafetyCheckerServer` inside `v2`; all validations are sent to an external server process or bypass using `NoOpSafetyChecker`.

```python
ok, msg = await client.validate_waypoint(current, next_loc)
ok, msg = await client.validate_takeoff(altitude, lat, lon)
ok, msg = await client.validate_landing(lat, lon)
```

### PreflightChecks

```python
from aerpawlib.v2.safety import PreflightChecks

ok = await PreflightChecks.run_all(vehicle)  # GPS fix, battery
```

### Connection monitoring

`vehicle.watch_disconnect(timeout)` detects heartbeat loss. The CLI races this against your runner. `setup_signal_handlers()` enables async-safe SIGINT/SIGTERM handling.

## Errors

| Situation | Result |
|-----------|--------|
| Validation fails | `can_*` returns `(False, message)` |
| AERPAW, no safety server | Process exits with critical error |
| Non-AERPAW, no server | `NoOpSafetyChecker` passes checks (development only) |

## See also

- `aerpawlib.v1.safety`: server YAML config and `SafetyCheckerServer`
- `aerpawlib.v2.vehicle`: connect with `safety=`
- `aerpawlib.cli`: `--safety-checker-port`, `--safety-checker-ip`
