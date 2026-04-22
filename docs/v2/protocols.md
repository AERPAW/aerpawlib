## Overview

`typing.Protocol` definitions for the v2 API. They exist so `ConnectionHandler`, safety checks, and tests can depend on a narrow surface while avoiding circular imports and weird structuring.

You shouldn't actually need to import these, they exist for testing and internal use.
`GPSProtocol` describes GPS fix and satellite count readers.
`VehicleProtocol` is the contract the connection and lifecycle code expects: connection flag, arming, position, home, battery, GPS, heading, and a `heartbeat_tick` hook.

### Usage
- In production code, real `Vehicle` / `Drone` / `Rover` instances satisfy these protocols naturally.
- In tests, you can hand-roll small stand-ins that implement the same properties without MAVSDK; `MockVehicle` in (``aerpawlib.v2.runner``) also covers a subset of needs.
