## Overview

Exception hierarchy for `aerpawlib.v1`.

All v1-specific exceptions derive from `AerpawlibError`, allowing callers to
catch either a broad framework error or a domain-specific subtype.

### Top-level families
- Connection: `AerpawConnectionError`, `ConnectionTimeoutError`,
  `HeartbeatLostError`, `PortInUseError`, `MAVSDKNotInstalledError`.
- Platform: `AERPAWPlatformError`, `NotInAERPAWEnvironmentError`.
- Commands: `ArmError`, `TakeoffError`, `NavigationError`, `RTLError`, etc.
- State/runtime: `StateError`, `NotConnectedError`, `AbortedError`.
- Validation: `ValidationError`, `InvalidToleranceError`,
  `InvalidAltitudeError`, `InvalidSpeedError`.
- State machine: `StateMachineError` and transition/build-time variants such
  as `NoEntrypointError`, `NoInitialStateError`, `InvalidStateError`.

### Usage notes
- Wrap lower-level exceptions with `original_error` where available so upstream
  handlers can inspect root causes.
- Prefer domain-specific subclasses for recoverable control flow in missions.

