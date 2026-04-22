## Overview

This module contains the constants for the v2 API.

The CLI, vehicles, runner, ZMQ multi-vehicle stack, and safety client all read from this module so the magic numbers are at least somewhat consistent.

### Groups
- Connection: `CONNECTION_TIMEOUT_S`, `HEARTBEAT_TIMEOUT_S`, `HEARTBEAT_CHECK_INTERVAL_S`, and related timing for `ConnectionHandler` and vehicle setup.
- Movement: default goto tolerance and timeout, heading tolerance, arming and takeoff delays, offboard/velocity loop delays, position readiness waits.
- Validation: min/max position tolerance for `can_goto` and similar checks.
- State machine: `STATE_MACHINE_DELAY_S` between state loop iterations.
- ZMQ: proxy in/out port strings, query timeout, and message type labels for transitions and field queries.
- Safety: `DEFAULT_SAFETY_CHECKER_PORT`, request names (`VALIDATE_WAYPOINT_REQ`, `VALIDATE_TAKEOFF_REQ`, etc.), and checker timeouts.
- AERPAW / platform: forward server address defaults, OEO timeout values, and environment flags used by the platform helpers.
- Geography: Earth radius and latitude correction coefficients shared with `Coordinate` / `VectorNED` math in `aerpawlib.v2.types`.
- QGC plans: command type IDs and default cruise speed for `.plan` parsing in `aerpawlib.v2.plan`.