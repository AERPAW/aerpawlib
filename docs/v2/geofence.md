## Overview

Polygon utilities for KML geofences and 2D spatial checks. Used by the safety server and available for custom validation in experiments.

## When to use this

Import when you need to test whether a planned point or path segment lies inside or crosses a geofence polygon.

## Common workflow

```python
from aerpawlib.v2 import read_geofence, inside, do_intersect

polygon = read_geofence("flight_area.kml")
if inside(lon=-78.696, lat=35.727, geofence=polygon):
    await drone.goto_coordinates(target)
```

## Key concepts

| Function | Description |
|----------|-------------|
| `read_geofence` | Load KML polygon vertices |
| `inside` | Point-in-polygon test |
| `do_intersect` | Test if two segments intersect |

## See also

- `aerpawlib.v1.util`: v1 geofence helpers
- `aerpawlib.v2.safety`: server-side enforcement
