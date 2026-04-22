## Overview

Legacy logging re-export module for v1 imports.

`aerpawlib.v1.log` exists for compatibility and forwards symbols from the
canonical `aerpawlib.log` module.

### Exports
- `LogLevel`
- `LogComponent`
- `ColoredFormatter`
- `configure_logging(...)`
- `get_logger(...)`
- `set_level(...)`

### Notes
- New code can import directly from `aerpawlib.log`.
- Existing v1 scripts can keep historical imports unchanged.

