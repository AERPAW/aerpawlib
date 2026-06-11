## Overview

Shared defaults and protocol constants for the v1 API (timeouts, tolerances, safety request names, ZMQ ports).

## When to use this

Reference when tuning mission parameters or integrating with the safety checker and ZMQ proxy. Most experiment scripts use CLI flags or method defaults instead of importing constants directly.

## Key concepts

| Group | Examples |
|-------|----------|
| Connection | Startup waits, heartbeat intervals, polling delays |
| Movement | Goto tolerance, timeout, rover mode values |
| Safety | Request name strings for `SafetyCheckerClient` |
| ZMQ | Proxy ports, query timeouts |
| Geography | Earth radius, coordinate conversion coefficients |

## See also

- `aerpawlib.v2.constants`: v2 defaults
- `aerpawlib.v1.safety`: safety protocol usage
