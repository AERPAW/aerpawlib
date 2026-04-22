## Overview

Safety API for v1 experiments.

This module provides the client/server components and wire-format helpers
used to validate mission commands against geofence and vehicle constraints.

High-level overview
-------------------
- `SafetyCheckerClient`
  - ZMQ REQ client used by vehicle/runner code to validate commands.
  - Sends compressed JSON requests and returns `(result, message)` tuples.
  - Uses send/receive timeouts and reconnects the socket after timeout.

- `SafetyCheckerServer`
  - Blocking ZMQ REP server that loads safety config from YAML and validates
    incoming requests.
  - Enforces include/exclude geofences, speed bounds, and (for copters)
    altitude bounds.
  - Stores a takeoff point used by landing-distance validation.

- Wire-format helpers (`serialize_request`, `serialize_response`, etc.)
  - Encode/decode zlib-compressed JSON dictionaries for the safety protocol.

## Primary symbols

Primary symbols provided by the safety module:

- `SafetyCheckerClient`
- `SafetyCheckerServer`
- `_polygon_edges`
- `serialize_msg`
- `deserialize_msg`
- `serialize_request`
- `serialize_response`

## Request types

The safety protocol uses request-function names from `aerpawlib.v1.constants`:

- `server_status_req`
- `validate_waypoint_req`
- `validate_change_speed_req`
- `validate_takeoff_req`
- `validate_landing_req`

These are routed by `SafetyCheckerServer.REQUEST_FUNCTIONS`.

## Usage

1. Start a safety server process with a YAML config.
2. Create a `SafetyCheckerClient` in mission code.
3. Call validation helpers before movement-related vehicle commands.
4. Continue only when validation returns `(True, "")`.

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
        print(f"Waypoint rejected: {msg}")
```

## Configuration expectations

`SafetyCheckerServer` expects a YAML file with:

- Required for all vehicle types:
  - `vehicle_type` (`"copter"` or `"rover"`)
  - `max_speed`
  - `min_speed`
  - `include_geofences` (KML paths)
  - `exclude_geofences` (KML paths)
- Additional required fields for copter:
  - `max_alt`
  - `min_alt`

Geofence paths are resolved relative to the config file directory.

## Errors

Client-side:

- `SafetyCheckerClient.send_request(...)` raises `TimeoutError` when the server
  does not reply within the configured timeout.
- On timeout, the client resets and reconnects its REQ socket before raising,
  so later requests can still proceed.
- `deserialize_msg(...)` raises `ValueError` for malformed compressed payloads
  or invalid JSON.

Server-side:

- Unknown request functions return `result=False` with an error message.
- Handler exceptions are caught and returned as `result=False` responses.
- Invalid config values during startup currently raise generic `Exception`
  (for missing keys or invalid `vehicle_type`).

Validation-result behavior (not exceptions):

- Waypoint violations return `(False, "...")`.
- Speed/takeoff/landing violations return `(False, "...")`.
- Landing validation fails if no takeoff location was recorded first.

## Implementation notes

- `SafetyCheckerServer(...)` starts a blocking server loop in `__init__`.
- ZMQ pattern is REQ/REP, so each request must receive exactly one reply.
- Waypoint path checks use polygon-edge intersection testing via
  `_polygon_edges(...)` and `do_intersect(...)`.
- Payloads are compressed JSON (`zlib`) to keep messages compact while staying
  human-readable after decompression.

## CLI

The package provides a legacy CLI entry via `main_cli`:

```bash
python -m aerpawlib.v1.safety --port 14580 --vehicle_config config.yaml
```

## Notes

- `aerpawlib.v1.safetyChecker` remains as a deprecated alias; use
  `aerpawlib.v1.safety` for new code.
