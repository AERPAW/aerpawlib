## Overview

AERPAW platform helpers used by v1 runtime internals.

This module provides HTTP-backed helpers for interacting with AERPAW services,
including OEO console logging, OEO topic publishing, and checkpoint state.

High-level overview
-------------------
- `AERPAW`
  - Eager client that checks platform reachability on construction.
  - Exposes helpers for OEO logging (`log_to_oeo`) and checkpoint read/write.
- `AERPAW_Platform`
  - Lazy singleton proxy that defers client construction until first use.

Primary capabilities
--------------------
- Platform connectivity probe (`attach_to_aerpaw_platform`).
- OEO message forwarding with severity filtering.
- Checkpoint booleans, counters, and string key/value coordination.
- User-topic publish helper for dashboard/experiment telemetry.

Behavior notes
--------------
- When services are unreachable, methods either return safely or raise a clear
  error depending on operation type.
- A one-time warning is emitted if platform-only features are used outside an
  AERPAW deployment.
- This module is primarily used by CLI/runtime plumbing rather than mission
  scripts directly.

