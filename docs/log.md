## Overview

The `aerpawlib.log` module is the shared logging foundation for the whole package. It provides:

- `LogLevel`: Enum aligned with the standard `logging` levels, plus `from_string()` for CLI strings.
- `LogComponent`: An empty *base* class. Do not add enum members on this type; use the versioned or CLI modules below for real component names.
- `ColoredFormatter`: Optional ANSI-colored console output for development.
- `configure_logging`: Attaches a stream handler (and optional file) under a *root* logger name (default `aerpawlib`).
- `get_logger`: Returns a `logging.Logger` for a dotted name, enum member, or object with a string `value`.
- `set_level`: Adjusts level on a specific logger (default root: `aerpawlib`).

This module should not be used by experiments, end users should either log using the `aerpawlib.v1.log` or `aerpawlib.v2.log` modules. This is because those modules actually implement the `LogComponent` class