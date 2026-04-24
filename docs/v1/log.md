## Overview

`aerpawlib.v1.log` defines the v1 logging surface: a `str`-based `LogComponent` enum and thin wrappers that default the configured root to `aerpawlib.v1`.

### `LogComponent` values

| Member                                 | Logger name (prefix)                                    |
|----------------------------------------|---------------------------------------------------------|
| `ROOT`                                 | `aerpawlib.v1`                                          |
| `VEHICLE`                              | `aerpawlib.v1.vehicle`                                  |
| `DRONE` / `ROVER`                      | `aerpawlib.v1.vehicle.drone` / `...rover`               |
| `SAFETY`                               | `aerpawlib.v1.safety`                                   |
| `RUNNER`                               | `aerpawlib.v1.runner`                                   |
| `TELEMETRY`                            | `aerpawlib.v1.telemetry`                                |
| `COMMAND`                              | `aerpawlib.v1.command`                                  |
| `NAVIGATION`                           | `aerpawlib.v1.navigation`                               |
| `CONNECTION`                           | `aerpawlib.v1.connection`                               |
| `GEOFENCE`                             | `aerpawlib.v1.geofence`                                 |
| `ZMQ`                                  | `aerpawlib.v1.zmq`                                      |
| `AERPAW` / `OEO` / `EXTERNAL` / `USER` | Mission and integration subsystems under `aerpawlib.v1` |
| `SITL`                                 | `aerpawlib.sitl` (simulation / test harness)            |

### API

- `get_logger(component=...)`: same behavior as :func:`aerpawlib.log.get_logger`, with default `LogComponent.ROOT`.
- `configure_logging(..., root_name=...)`:  defaults `root_name` to `aerpawlib.v1` so v1 child loggers receive handlers.
- `set_level(level, component=None)`: when `component` is omitted, adjusts the v1 root (`LogComponent.ROOT`).

`LogLevel` and `ColoredFormatter` are re-exported here for convenience alongside v1 configuration.

### Importing

In v1 mission and vehicle code, use:

```python
from aerpawlib.v1.log import LogComponent, get_logger
```