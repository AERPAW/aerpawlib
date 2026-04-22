## Overview

Small test helpers for v2. Primarily exposes `MockVehicle`, a minimal vehicle stand-in with configurable position, home, armed, and connected flags, plus static `Battery` and `GPSInfo` for unit tests of runner logic that does not need a real vehicle.

### Behavior notes
- The mock is intentionally incomplete compared to a real `Vehicle`; do not use it to validate MAVLink behavior, only to exercise control flow in your own classes.
- For end-to-end runner tests, combine `MockVehicle` or `DummyVehicle` with the v2 `Runner` classes as shown in the repository’s unit tests.
