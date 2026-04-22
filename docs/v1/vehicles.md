## Overview

Vehicle implementation package for v1.

This package re-exports shared and concrete vehicle implementations used by the
`aerpawlib.v1.vehicle` compatibility module and by internal runtime code.

Exports
-------
- `Vehicle`: MAVSDK-backed base class with lifecycle and telemetry plumbing.
- `DummyVehicle`: no-op/testing shim.
- `Drone`: multirotor implementation.
- `Rover`: ground vehicle implementation.

Usage notes
-----------
- Mission scripts typically import these via `aerpawlib.v1` or
  `aerpawlib.v1.vehicle`.
- Import from `aerpawlib.v1.vehicles` only when direct access to implementation
  package symbols is needed.

