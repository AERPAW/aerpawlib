## Overview

`ExternalProcess` is the v2 subprocess helper.

It wraps `asyncio.create_subprocess_exec` so mission code can tail stdout, feed stdin, and wait for regex-matched output without blocking the main event loop, unlike v1 where blocking was much more difficult to get around.

You will use it when a mission needs a sidecar (sensor bridge, custom bridge process, SITL helper) running alongside aerpawlib, all orchestrated from the same `asyncio` program.

### Capabilities
- `start`: launch with executable plus argv list, optional stdio to files.
- `read_line`: incremental stdout reads as lines.
- `send_input`: write bytes to the subprocess stdin when a pipe is open.
- `wait_until_output` / `wait_until_terminated`: awaitable completion and pattern matching on output.
- `aclose`: async cleanup to avoid leaving transports around, especially in tests.

### Behavior notes
- `wait_until_output` requires a piped stdout; if you redirect stdout to a file, the streaming helpers cannot read it.
- If stdin is not available, `send_input` will raise `RuntimeError`, matching the guardrails described in the v1 external doc and preserved in v2.
