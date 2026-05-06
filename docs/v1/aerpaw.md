## Overview

AERPAW platform helpers used by the v1 runtime internals.

This module provides HTTP-backed helper utilities for interacting with AERPAW services,
including Operator Experimenter Override (OEO) console logging, OEO topic publishing, and checkpoint state management.

### High-Level Overview
- `AERPAW`
  - Eager client that verifies platform reachability upon initialization.
  - Exposes helpers for OEO logging (e.g., `log_to_oeo`) and checkpoint read/write operations.
- `AERPAW_Platform`
  - Lazy singleton proxy that defers the `AERPAW` client construction until its first use.

### Primary Capabilities
- Platform connectivity probe (`attach_to_aerpaw_platform`).
- OEO message forwarding with severity filtering.
- Checkpoint booleans, counters, and string key/value coordination.
- User-topic publish helper for dashboard and experiment telemetry.

### Behavioral Notes
- When services are unreachable, methods will either return safely or raise a clear
  error depending on the operation type.
- A one-time warning is emitted if platform-exclusive features are invoked outside of an
  AERPAW deployment.
- This module is primarily used by CLI and runtime plumbing rather than directly by mission
  scripts.
