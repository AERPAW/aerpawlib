This module contains helpful classes and functions that may be useful to you.
Here is a breakdown of the core utilities and how to use them effectively.

## Geometry

Handling physical locations and movements is notoriously tricky, but `aerpawlib` simplifies this by overriding standard Python operators to let you do intuitive spatial math.

* `Coordinate`: Represents an absolute WGS84 physical location. *Note: In v1 workflows, `alt` (altitude) is always relative to the vehicle's home location.*
* `VectorNED`: A 3D vector representing movement in the NED (North, East, Down) coordinate frame.
* `Waypoint`: A structural wrapper used for routing.

Note:
* You can add a vector to a coordinate to get a new target destination (`Coordinate + VectorNED = Coordinate`). This uses a geodesic approximation based on Earth-radius constants, which is perfectly accurate for mission-scale drone movements.
* You can subtract one coordinate from another to find the vector between them (`Coordinate - Coordinate = VectorNED`). In the NED convention, the `down` component is calculated as `other.alt - self.alt`.

## Geofence Helpers

When dealing with autonomous flight, keeping your drone inside safe operational zones is paramount. 

* Parsing KMLs: Use `read_geofence(...)` to parse standard KML polygons directly into memory. 
* Spatial Logic: The module provides robust geometry predicates like `inside(...)` (which uses ray-casting algorithms to determine if a point is within a polygon) and `do_intersect(...)` (which tests if a flight path segment crosses a geofence boundary).

> **Deprecation**: You might notice camelCase aliases in the code, such as `readGeofence` or `doIntersect`. These are kept purely for backward compatibility with older AERPAW scripts. Be kind to your future self and stick to Pythonic `snake_case` in your new code.

## Plan Parsing

If you prefer to draw your missions visually using QGroundControl, this module seamlessly translates those `.plan` files into actionable code.

* `read_from_plan` & `read_from_plan_complete`: These functions ingest QGroundControl `.plan` files and convert them into standard waypoint structures. 
* Smart Extraction: The parser understands core commands (like takeoff, waypoints, speed changes, and RTL). It safely extracts what it needs and ignores unknown commands, preventing strange UI configurations from crashing your script.

---

## Example

Here is a quick example of how cleanly you can combine coordinate math and plan parsing in your mission logic:

```python
from aerpawlib.v1.util import Coordinate, VectorNED, read_from_plan

# 1. Define a starting point
origin = Coordinate(35.7275, -78.6960, 10)

# 2. Define a movement vector (20 meters North)
step = VectorNED(20, 0, 0)

# 3. Calculate the absolute destination
target = origin + step

# 4. Load a pre-planned visual mission
waypoints = read_from_plan("mission.plan")
```
