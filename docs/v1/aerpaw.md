## Overview

AERPAW platform integration for v1: OEO logging, checkpoints, and forward-server connectivity. Used by the CLI and runtime; mission scripts rarely import this directly.

## When to use this

Reference when you need OEO console output or checkpoint coordination on the AERPAW testbed. Use `--no-aerpaw-environment` for local SITL without platform services.

## Key concepts

| Symbol | Description |
|--------|-------------|
| `AERPAW` | Eager client; probes platform on init |
| `AERPAW_Platform` | Lazy singleton for deferred connection |
| `log_to_oeo` | Forward messages to OEO with severity |
| Checkpoint helpers | Boolean, counter, and string state on the platform |

Unreachable services return safe defaults or raise clear errors depending on the operation.

## See also

- `aerpawlib.v2.aerpaw`: v2 platform helper
- `aerpawlib.cli`: `--no-aerpaw-environment`
