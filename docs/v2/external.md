## Overview

Async wrapper for sidecar subprocesses in v2 missions (sensor bridges, helper tools).

## When to use this

Import `ExternalProcess` when your experiment launches and communicates with an external process on the same asyncio loop.

## Common workflow

```python
from aerpawlib.v2 import ExternalProcess

proc = ExternalProcess("python3", params=["-u", "sensor_reader.py"])
await proc.start()
line = await proc.read_line()
await proc.send_input("start\n")
lines = await proc.wait_until_output(r"READY")
await proc.wait_until_terminated()
await proc.aclose()
```

## Key concepts

| Method | Description |
|--------|-------------|
| `start` | Launch with executable + argv list |
| `read_line` | Read stdout line (piped mode) |
| `send_input` | Write to stdin |
| `wait_until_output` | Await regex match on stdout |
| `wait_until_terminated` | Await process exit |
| `aclose` | Async cleanup |

> **Note:** `wait_until_output` requires piped stdout. `send_input` raises if stdin is unavailable.

## See also

- `aerpawlib.v1.external`: v1 subprocess helper
