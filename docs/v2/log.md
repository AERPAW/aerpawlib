## Overview

Logging wrapper for the v2 stack. It reuses `aerpawlib.log`’s `configure_logging` and `get_logger` but tags messages with v2 component names so operator dashboards and file logs are easy to filter by subsystem.

`LogComponent` groups well-known string keys (`ROOT`, `VEHICLE`, `DRONE`, `ROVER`, `SAFETY`, `RUNNER`, `AERPAW`, `ZMQ`, and related paths). Pass a component to `get_logger` when you are extending the library, or use the default root logger in application code.

### Primary symbols
- `LogComponent`:  dotted logger name constants for v2.
- `get_logger(component=...)`:  return a `logging.Logger` for that component.
- `configure_logging(...)`:  v2-tuned entry point to `aerpawlib.log` configuration.
- `set_level(...)`:  adjust verbosity in line with shared aerpawlib log settings.

### Behavior notes
- Mission code typically does not reconfigure logging; the CLI and experiment host set that up. Use this module when you are adding a new v2 submodule and want consistent names in log output.
