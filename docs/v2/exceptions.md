## Overview

v2’s exception model centers on `AerpawlibError`, a base type that carries a human-readable `message`, a stable `code`, a `severity` string (`"warning"`, `"error"`, `"critical"`), and sometimes `original_error` for the underlying stack exception.

Catching `AerpawlibError` at the top level of a mission is a good way to log, notify OEO, and exit cleanly. 

More specific subtypes help you decide whether a fault is worth retrying or should abort the experiment.

### Top-level families
- Connection `AerpawConnectionError` and `ConnectionTimeoutError`, `HeartbeatLostError`, `PortInUseError`, and related conditions when the MAVSDK link or gRPC port fails.
- Command `CommandError` with `ArmError`, `DisarmError`, `TakeoffError`, `LandingError`, `NavigationError`, `VelocityError`, `RTLError` for failed vehicle actions.
- State `StateError`, `NotArmableError`, `NotConnectedError`, and `UnexpectedDisarmError` when the aircraft arms/disarms in ways that violate the mission state machine.
- Runner `RunnerError` for mis-decorated scripts, missing entrypoints, and invalid state transitions; includes `NoEntrypointError`, `NoInitialStateError`, `InvalidStateError`, and friends.
- Plan `PlanError` when a `.plan` file cannot be parsed.
- There may be additional narrow types in the package; import from `aerpawlib.v2` for the public set.