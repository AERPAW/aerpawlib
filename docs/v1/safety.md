## Overview

Validate mission commands against geofences, speed limits, and altitude bounds before the vehicle moves. The safety module provides a ZMQ client for experiment scripts and a server that loads YAML configuration.

## When to use this

Use `SafetyCheckerClient` in v1 scripts that must respect AERPAW geofence rules. Run `SafetyCheckerServer` (or `aerpawlib-safety-checker`) with a YAML config on the testbed. The CLI attaches a client with `--safety-checker-port` / `--safety-checker-ip`. Helper extra args `--safety_checker_ip` / `--safety_checker_port` are passed through to the script and also used when attaching that client. On AERPAW the default host is this node's C-VM XV (`AP_EXPENV_CVM_<n>_XV`). After that, `takeoff`, `goto_coordinates`, `land`, and `set_groundspeed` ask the server first and do not run if the maneuver is rejected.

## Common workflow

```python
from aerpawlib.v1 import Coordinate
from aerpawlib.v1.safety import SafetyCheckerClient

with SafetyCheckerClient("127.0.0.1", 14580) as checker:
    ok, msg = checker.check_server_status()
    if not ok:
        raise RuntimeError(msg)

    cur = Coordinate(35.7275, -78.6960, 10)
    nxt = Coordinate(35.7280, -78.6955, 15)
    ok, msg = checker.validate_waypoint_command(cur, nxt)
    if not ok:
        print(f"Rejected: {msg}")
```

> **Note:** Validation methods return `(bool, str)`. Always check the boolean before executing the maneuver.

## Key concepts

### SafetyCheckerClient

Use this from your script to ask the safety server about a maneuver. Methods include `check_server_status`, `validate_waypoint_command`, `validate_takeoff_command`, `validate_landing_command`, and `validate_change_speed_command`.

> **Note:** These calls wait for the server. If a request times out, the next call tries again.

### SafetyCheckerServer

ZMQ REP server loading YAML limits:

| Key | Required | Description |
|-----|----------|-------------|
| `vehicle_type` | All | `copter` or `rover` |
| `max_speed` / `min_speed` | All | Speed limits |
| `include_geofences` | All | KML paths (allowed regions) |
| `exclude_geofences` | All | KML paths (forbidden regions) |
| `max_alt` / `min_alt` | Copter | Altitude limits (AERPAW copter `min_alt` is typically 20 m) |

Copter landing must be within 5 m of the recorded takeoff location.

KML paths resolve relative to the YAML file location.

### Server CLI

```bash
aerpawlib-safety-checker --port 14580 --vehicle_config config.yaml
```

## Errors

| Issue | Meaning |
|-------|---------|
| `TimeoutError` | Server did not respond; client resets socket |
| `(False, msg)` from validation | Maneuver rejected by policy |
| Server startup `Exception` | Invalid or incomplete YAML config |

> **Note:** Use `aerpawlib.v1.safety`, not the deprecated `aerpawlib.v1.safetyChecker` alias.

## See also

- `aerpawlib.v2.safety`: v2 `can_*` integration with the same server
- `aerpawlib.v1.vehicle`: commands that call the attached client
- `aerpawlib.cli`: `--safety-checker-port`, `--safety-checker-ip` (v1 and v2; helper extra args `--safety_checker_ip` / `--safety_checker_port` are also honored)
