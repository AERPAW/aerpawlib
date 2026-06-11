## Overview

`typing.Protocol` definitions describing the vehicle and GPS surfaces for internal use, safety checks, and tests.

## When to use this

Experiment scripts do not need these types. Import when writing tests or extensions that depend on a minimal vehicle interface without circular imports.

## Key concepts

| Protocol | Description |
|----------|-------------|
| `GPSProtocol` | GPS fix and satellite count readers |
| `VehicleProtocol` | Connection lifecycle, telemetry, arming, `watch_disconnect` |

`Drone`, `Rover`, and `MockVehicle` satisfy these protocols.

## See also

- `aerpawlib.v2.testing`: `MockVehicle` test double
- `aerpawlib.v2.vehicle`: concrete implementations
