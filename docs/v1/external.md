## Overview

Async wrapper for sidecar subprocesses in v1 missions (sensor bridges, helper tools).

## When to use this

Import `ExternalProcess` when your experiment launches and communicates with an external process from runner code.

## Common workflow

```python
from aerpawlib.v1.external import ExternalProcess

proc = ExternalProcess("python3", params=["-u", "sensor_reader.py"])
await proc.start()
line = await proc.read_line()
await proc.send_input("start\n")
await proc.wait_until_terminated()
await proc.aclose()
```

## Key concepts

| Method | Description |
|--------|-------------|
| `start` | Launch subprocess |
| `read_line` | Read stdout line (piped mode) |
| `send_input` | Write to stdin |
| `wait_until_output` | Await regex match on stdout |
| `wait_until_terminated` | Await process exit |
| `aclose` | Async cleanup |

> **Note:** `wait_until_output` requires piped stdout, not file redirection.

## See also

- `aerpawlib.v2.external`: v2 subprocess helper (`create_subprocess_exec`)
