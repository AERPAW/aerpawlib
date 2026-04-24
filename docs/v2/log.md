## Overview

`aerpawlib.v2.log` tags messages with v2 component names so operator dashboards and file logs are easy to filter by subsystem. It subclasses the empty `aerpawlib.log.LogComponent` base and adds string constants for the v2 stack.

It reuses `aerpawlib.log.configure_logging` and `aerpawlib.log.get_logger` but sets the default `root_name` to `aerpawlib.v2`.

### `LogComponent` values

| Member            | Logger name                               |
|-------------------|-------------------------------------------|
| `ROOT`            | `aerpawlib.v2`                            |
| `VEHICLE`         | `aerpawlib.v2.vehicle`                    |
| `DRONE` / `ROVER` | `aerpawlib.v2.vehicle.drone` / `...rover` |
| `SAFETY`          | `aerpawlib.v2.safety`                     |
| `RUNNER`          | `aerpawlib.v2.runner`                     |
| `AERPAW`          | `aerpawlib.v2.aerpaw`                     |
| `ZMQ`             | `aerpawlib.v2.zmq`                        |

### Primary symbols

- `LogComponent`: Dotted logger name constants for v2.
- `get_logger(component=...)`: Return a `logging.Logger` for that component.
- `configure_logging(...)`: v2-tuned entry point; default root is `aerpawlib.v2`.
- `set_level(...)`: Adjust verbosity in line with shared aerpawlib log settings.
