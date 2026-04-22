## Overview

Core dataclasses and spatial types for the v2 API. These types are what you pass into vehicle commands, read from telemetry properties, and combine in mission math.

aerpawlib uses absolute horizontal positions (WGS84 latitude and longitude) with altitude in meters, using the same NED (north, east, down) vector conventions as v1 to make migration as painless as possible.
### Primary types
- `Coordinate`:  lat, lon, alt. Operators combine with `VectorNED` for mission-scale moves; methods include `bearing` to another coordinate, `distance_2d`, and helpers used by validation.
- `VectorNED`:  north, east, down in meters. Supports rotation, `norm`, `cross_product`, addition with coordinates, and subtraction between coordinates to get displacement.
- `Battery`:  voltage, current, remaining percent (where available from the stack).
- `GPSInfo`:  fix type and satellite count for preflight and logging.
- `Attitude`:  roll, pitch, yaw in radians.
- `Waypoint`:  type alias for parsed plan tuples where used by `plan` (see [plan](plan.md)).