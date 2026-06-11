## Overview

Load QGroundControl `.plan` files into waypoint structures your mission can iterate.

## When to use this

Import when you design missions in QGC and execute them from a v2 runner script.

## Common workflow

```python
from pathlib import Path

from aerpawlib.v2.plan import read_from_plan, get_location_from_waypoint

for wp in read_from_plan(Path("mission.plan")):
    coord = get_location_from_waypoint(wp)
    await drone.goto_coordinates(coord)
```

## Key concepts

| Function | Description |
|----------|-------------|
| `read_from_plan` | Navigation waypoints as tuples |
| `read_from_plan_complete` | All items (takeoff, RTL, etc.) as dicts |
| `get_location_from_waypoint` | Build `Coordinate` from a waypoint tuple |

Unknown QGC items are skipped when possible. Verify critical legs in SITL before field deployment.

Plan command IDs live in `aerpawlib.v2.constants`.

## Errors

`PlanError`: missing file, invalid JSON, or malformed mission items.

## See also

- `aerpawlib.v2.vehicle`: `goto_coordinates`
- `aerpawlib.v1.util`: v1 plan parsing (`str` paths)
