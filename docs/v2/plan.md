## Overview

QGroundControl **`.plan`** importers. If you build missions in QGC, you can check them in next to your script and parse the waypoint stream into tuples the vehicle layer understands.

### Primary functions
- `read_from_plan`:  return a list of `Waypoint` tuples `(command, x/lat, y/lon, z/alt, waypoint_id, speed)` for navigation commands, using sensible defaults for speed when missing in the file.
- `read_from_plan_complete`:  return a list of per-item **dicts** with `id`, `command`, `pos`, `wait_for`, and `speed` for takeoff, waypoint, and RTL items so you can mirror the full QGC mission structure in code.
- `get_location_from_waypoint`:  build a `Coordinate` from a `Waypoint` tuple (lat, lon, alt from the tuple’s position fields).

### Error handling
- `PlanError` (subclass of `AerpawlibError`) is raised for missing files, invalid JSON, or malformed mission items, often wrapping the original exception in `original_error` for debug logs.

### Behavior notes
- Command constants (`PLAN_CMD_*`) live in [constants](constants.md) and stay aligned with the parser and ArduPilot mission expectations.
- Unknown mission items are skipped where possible so odd QGC configurations do not crash the parser. Verify critical legs in SITL before field deployment.

The [v2 README](README.md) has a short example loop over `read_from_plan`.
