## Overview

`typing.Protocol` definitions for the v2 API. They exist so safety checks, disconnect monitoring, and tests can depend on a narrow surface while avoiding circular imports.

You shouldn't actually need to import these; they exist for testing and internal use.
`GPSProtocol` describes GPS fix and satellite count readers.
`VehicleProtocol` is the contract for connection lifecycle and telemetry: `connected`, `closed`, `watch_disconnect()`, arming, position, home, battery, GPS, heading, and `heartbeat_tick`.

### Usage
- In production code, real `Vehicle` / `Drone` / `Rover` instances satisfy these protocols naturally.
- In tests, you can hand-roll small stand-ins that implement the same properties without MAVSDK; `MockVehicle` in (``aerpawlib.v2.runner``) also covers a subset of needs.
