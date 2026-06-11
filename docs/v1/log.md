## Overview

Versioned logging for v1 experiment and library code. Tag messages by subsystem for console and file output.

## When to use this

Import in v1 mission or library code when you need structured debug output.

## Common workflow

```python
from aerpawlib.v1.log import LogComponent, get_logger

logger = get_logger(LogComponent.VEHICLE)
logger.info("Starting measurement leg")
```

Enable verbose CLI output with `-v` / `--verbose`; write DEBUG to a file with `--log-file`.

## Key concepts

| Component | Logger name |
|-----------|-------------|
| `VEHICLE`, `DRONE`, `ROVER` | Vehicle subsystems |
| `RUNNER` | Runner execution |
| `SAFETY` | Safety checker |
| `NAVIGATION`, `COMMAND` | Flight commands |
| `ZMQ` | Multi-vehicle messaging |

`configure_logging` defaults the root logger to `aerpawlib.v1`.

## See also

- `aerpawlib.log`: shared logging foundation
- `aerpawlib.cli`: `-v`, `--log-file`, `--structured-log`
- `aerpawlib.v2.log`: v2 components
