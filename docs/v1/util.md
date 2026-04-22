## Overview

Utility API for v1 experiments.

This module provides geometry, geofence, plan parsing, and local port helper
utilities used across v1 runners, vehicles, and safety components.

High-level overview
-------------------
- Geometry (`Coordinate`, `VectorNED`, `Waypoint`)
  - Coordinate math for WGS84 positions and NED vectors.
  - Distance, bearing, vector arithmetic, and JSON helpers.

- Geofence helpers
  - Parse KML polygons (`read_geofence`) and evaluate geometry predicates
    (`inside`, `do_intersect`, etc.).
  - Includes camelCase aliases for backward compatibility.

- Plan parsing (`read_from_plan`, `read_from_plan_complete`)
  - Parse QGroundControl `.plan` mission items into waypoint structures.
  - Track speed-change commands and expose mission location helpers.

- Port checks (`is_udp_port_in_use`, `is_tcp_port_in_use`)
  - Lightweight local bind checks used during startup validation.

## Primary symbols

Key symbols provided by the util module:

- Geometry:
  - `Coordinate`
  - `VectorNED`
  - `Waypoint`

- Plan I/O:
  - `read_from_plan`
  - `read_from_plan_complete`
  - `get_location_from_waypoint`

- Geofence:
  - `read_geofence` / `readGeofence`
  - `inside`
  - `lies_on_segment` / `liesOnSegment`
  - `orientation`
  - `do_intersect` / `doIntersect`

- Ports:
  - `is_udp_port_in_use`
  - `is_tcp_port_in_use`

## Usage

```python
from aerpawlib.v1.util import Coordinate, VectorNED, read_from_plan

origin = Coordinate(35.7275, -78.6960, 10)
step = VectorNED(20, 0, 0)
target = origin + step

waypoints = read_from_plan("mission.plan")
```

## Errors

Geometry:

- `Coordinate.distance(...)`, `Coordinate.ground_distance(...)`, and
  `Coordinate.bearing(...)` raise `TypeError` if the argument is not a
  `Coordinate`.
- `VectorNED` arithmetic and cross product raise `TypeError` on invalid types.

Plan parsing:

- `read_from_plan(...)` and `read_from_plan_complete(...)` raise `Exception`
  when `fileType != "Plan"`.
- Both readers raise `ValueError` if a mission item has fewer than 7 params.
- Unknown mission commands are skipped (not raised) unless they affect parsing
  assumptions.

Geofence:

- `read_geofence(...)` assumes the expected KML polygon structure and may raise
  parse/file errors if the file is missing or malformed.

Ports:

- `is_udp_port_in_use(...)` returns True for any bind failure.
- `is_tcp_port_in_use(...)` returns True only for `EADDRINUSE`; other socket
  errors are re-raised.

## Implementation notes

- `Coordinate + VectorNED` computes a geodesic approximation using Earth-radius
  constants; this is intended for mission-scale movements.
- `Coordinate - Coordinate` returns a `VectorNED` where `down` is
  `other.alt - self.alt` (NED convention).
- `inside(...)` uses ray casting; segment checks use orientation tests in
  `do_intersect(...)`.
- CamelCase aliases (`readGeofence`, `doIntersect`, etc.) exist for backward
  compatibility; prefer snake_case in new code.

## Notes

- Prefer imports from `aerpawlib.v1.util` to keep mission code version-stable.
- `Coordinate.alt` is relative to vehicle home conventions in v1 movement
  workflows.
- `.plan` parsing supports core commands (takeoff, waypoint, speed, RTL) used
  by v1 helpers.
