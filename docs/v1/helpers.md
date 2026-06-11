## Overview

Internal helper utilities for the v1 implementation (polling, heading math, thread-safe values). Not part of the typical experiment author workflow.

## When to use this

Reference when maintaining v1 vehicle or runner internals. Experiment scripts should use `aerpawlib.v1.util` for coordinates and public APIs for movement.

## Key concepts

| Symbol | Description |
|--------|-------------|
| `wait_for_condition` | Poll until predicate is true |
| `validate_tolerance` | Bounds-check goto tolerance |
| `normalize_heading` / `heading_difference` | Heading math |
| `ThreadSafeValue` | Thread-safe wrapper for v1 dual-loop telemetry |

## See also

- `aerpawlib.v1.util`: public spatial types
- `aerpawlib.v1.vehicle`: high-level commands
