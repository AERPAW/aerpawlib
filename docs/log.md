## Overview

Shared logging foundation for all aerpawlib versions: levels, formatters, and root configuration.

## When to use this

Use `aerpawlib.v1.log` or `aerpawlib.v2.log` in experiment scripts. Import this module only when extending the library or CLI logging setup.

## Key concepts

| Symbol | Description |
|--------|-------------|
| `LogLevel` | Enum aligned with standard logging levels |
| `LogComponent` | Empty base class; real components live in v1/v2/cli modules |
| `configure_logging` | Attach console and optional file handlers |
| `get_logger` | Return a named logger |
| `ColoredFormatter` | ANSI-colored console output for development |

## See also

- `aerpawlib.v1.log`: v1 component names
- `aerpawlib.v2.log`: v2 component names
- `aerpawlib.cli.log`: CLI components
