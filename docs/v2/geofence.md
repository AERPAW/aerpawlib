## Overview

Geometric helpers for working with **KML** polygons and 2D checks. The module was factored out of the old v1 `util` package so v2 can import geofence logic without dragging in the entire legacy surface.

`read_geofence` walks a KML document, finds a polygon ring, and returns a list of `{ "lat", "lon" }` points. `inside` answers whether a WGS point lies in a polygon, and `do_intersect` tests two line segments in lon/lat space. These are the same building blocks the safety server uses when validating that planned paths do not cut through excluded areas.

### Primary functions
- `read_geofence` — load polygon vertices from a KML file; raises if no ring is found.
- `inside` / related predicates — check containment for mission or validation logic.
- `do_intersect` — test segment–segment intersection for path checks.