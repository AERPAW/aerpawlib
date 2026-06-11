## Overview

Shared defaults and protocol constants for the v2 API (timeouts, tolerances, safety request names, ZMQ ports, plan command IDs).

## When to use this

Reference when tuning mission parameters or reading safety/ZMQ protocol values. Most experiment scripts rely on CLI flags and method defaults.

## Key concepts

| Group | Examples |
|-------|----------|
| Connection | `CONNECTION_TIMEOUT_S`, `HEARTBEAT_TIMEOUT_S` |
| Movement | Default goto tolerance, heading tolerance, arm delays |
| Validation | Min/max position tolerance for `can_goto` |
| ZMQ | Proxy ports, message type labels |
| Safety | `DEFAULT_SAFETY_CHECKER_PORT`, validation request names |
| Plans | QGC command type IDs, default cruise speed |

## See also

- `aerpawlib.v1.constants`: v1 defaults
- `aerpawlib.v2.plan`: plan parsing constants
