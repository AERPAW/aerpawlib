## Overview

Shared constants for `aerpawlib.v1`.

This module centralizes defaults and protocol values used across v1 vehicle,
runner, safety, and platform integrations.

Groups
------
- Connection/timeouts: startup waits, heartbeat intervals, polling delays.
- Movement: tolerances, goto timeout, rover mode constants.
- Safety protocol: request names and checker client/server defaults.
- ZMQ: proxy ports, message type labels, query timeout values.
- AERPAW platform: forward-server defaults and OEO severity labels.
- Geography/math: Earth constants and coordinate conversion coefficients.

Usage notes
-----------
- Treat these values as runtime defaults; adjust behavior via higher-level
  configuration or arguments instead of mutating constants in mission code.
- Several values are safety-sensitive (`*_TIMEOUT_*`, tolerance bounds,
  safety request names) and are consumed by multiple modules.

