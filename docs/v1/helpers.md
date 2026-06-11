## Overview

Small reusable helper primitives for v1 internals.

This module provides async polling helpers, heading/tolerance utilities, and a
thread-safe value wrapper used by the v1 dual-loop architecture.

### Primary symbols
- `wait_for_condition(...)`: poll until a predicate is true with optional
  timeout.
- `wait_for_value_change(...)`: specialized polling for equality transitions.
- `validate_tolerance(...)`: bounds-check mission tolerances and raise
  `InvalidToleranceError` when out of range.
- `normalize_heading(...)` and `heading_difference(...)`: heading math helpers.

