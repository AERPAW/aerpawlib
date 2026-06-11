## Overview

Spatial types, geofence helpers, and QGroundControl plan parsing for v1 experiments.

## When to use this

Import `Coordinate`, `VectorNED`, and plan helpers when you compute waypoints or load `.plan` files in v1 scripts.

## Common workflow

```python
from aerpawlib.v1.util import Coordinate, VectorNED, read_from_plan

origin = Coordinate(35.7275, -78.6960, 10)
target = origin + VectorNED(20, 0, 0)

waypoints = read_from_plan("mission.plan")
```

## Key concepts

| Symbol | Description |
|--------|-------------|
| `Coordinate` | WGS84 lat/lon; altitude relative to home |
| `VectorNED` | North, east, down offset in metres |
| `Coordinate + VectorNED` | New target position |
| `Coordinate - Coordinate` | Displacement vector |
| `read_geofence` | Parse KML polygon to `{lat, lon}` list |
| `inside` | Point-in-polygon test |
| `do_intersect` | Segment intersection test |
| `read_from_plan` | Navigation waypoints from QGC `.plan` |

> **Note:** Prefer `snake_case` names (`read_geofence`). CamelCase aliases exist for legacy scripts.

## See also

- `aerpawlib.v1.vehicle`: pass coordinates to `goto_coordinates`
- `aerpawlib.v2.types`: v2 spatial types
- `aerpawlib.v2.plan`: v2 plan parsing (`pathlib.Path`)
