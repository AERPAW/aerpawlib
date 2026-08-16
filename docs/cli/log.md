## Overview

Logging component names for the CLI orchestration layer.

## When to use this

Reference when extending CLI startup, config merge, or structured log wiring. Experiment scripts use `aerpawlib.v1.log` or `aerpawlib.v2.log`.

## Key concepts

| Component | Logger name |
|-----------|-------------|
| `ROOT` | `aerpawlib` |
| `CLI` | `aerpawlib.cli` |
| `STRUCTURED` | `aerpawlib.structured` |

## See also

- `aerpawlib.log`: shared logging API
- `aerpawlib.cli`: CLI flags for verbosity and log files
