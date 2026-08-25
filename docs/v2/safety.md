## Overview

Validate commands before flight and integrate with the AERPAW SafetyCheckerServer. Vehicles expose `can_takeoff`, `can_goto`, and `can_land`; pass a `SafetyCheckerClient` at connect time or set `vehicle.safety`.

## When to use this

- Check takeoff, goto, and land before you send them
- Enforce geofence and altitude rules on the AERPAW testbed (server required)
- Run locally without a server (checks pass, with a warning)

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

The CLI attaches the client with `--safety-checker-port` / `--safety-checker-ip` (required on AERPAW). Helper extra args `--safety_checker_ip` / `--safety_checker_port` are passed through to the script and also used when attaching that client. On AERPAW the default host is the C-VM (`AP_EXPENV_OEOCVM_XM`, typically `192.168.32.25`), not E-VM localhost. `takeoff`, `goto_coordinates`, `land`, and `set_groundspeed` then check first and raise if the server rejects the maneuver.

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
| Non-AERPAW | Passthrough (all checks pass, warning logged) | Connect to `127.0.0.1` unless `--safety-checker-ip` is set, or fall back to passthrough |
| AERPAW | C-VM (`AP_EXPENV_OEOCVM_XM`) port 14580; failure exits | Connect or exit |

### SafetyCheckerClient

Ask the safety server from your script with `await`. v2 does not ship a server of its own: use `aerpawlib-safety-checker` (the v1 server) on the testbed, or omit the client locally.

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

If the vehicle link is lost, the CLI stops the mission and does not RTL. Ctrl-C also stops the runner without RTL. Auto RTL/RTH runs only after a successful mission, unless you pass `--skip-rtl`.

## Errors

| Situation | Result |
|-----------|--------|
| Validation fails | `can_*` returns `(False, message)`; takeoff/goto/land raise if you call them anyway |
| AERPAW, no safety server | The process exits |
| Local / SITL, no server | Checks pass (with a warning) |

## See also

- `aerpawlib.v1.safety`: server YAML config and `SafetyCheckerServer`
- `aerpawlib.v2.vehicle`: connect with `safety=`
- `aerpawlib.cli`: `--safety-checker-port`, `--safety-checker-ip` (helper extra args `--safety_checker_ip` / `--safety_checker_port` are also honored)
