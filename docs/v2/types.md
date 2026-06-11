## Overview

Core dataclasses and spatial types for the v2 API. Pass these into vehicle commands, read them from telemetry, and combine them in mission math.

## When to use this

Import from `aerpawlib.v2.types` (or `aerpawlib.v2`) for coordinates, vectors, and telemetry structures.

## Common workflow

```python
from aerpawlib.v2 import Coordinate, VectorNED

home = Coordinate(35.7275, -78.6960, 10)
north_20m = home + VectorNED(20, 0, 0)
bearing = home.bearing(north_20m)
```

## Key concepts

| Type | Description |
|------|-------------|
| `Coordinate` | lat, lon, alt (m AGL relative to home) |
| `VectorNED` | north, east, down in metres |
| `Battery` | voltage, current, remaining % |
| `GPSInfo` | fix type, satellite count |
| `Attitude` | roll, pitch, yaw (radians) |
| `Waypoint` | Plan tuple alias (see `aerpawlib.v2.plan`) |

Horizontal positions are absolute WGS84; NED conventions match v1 for migration.

## See also

- `aerpawlib.v2.vehicle`: telemetry properties use these types
- `aerpawlib.v2.plan`: waypoint tuples from QGC files
- `aerpawlib.v1.util`: v1 equivalents
