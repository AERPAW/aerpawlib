## Overview

Async subprocess helper for v1 flows.

`ExternalProcess` is a small wrapper around `asyncio.create_subprocess_shell`
used to start and monitor sidecar processes (for example SITL tools or local
infrastructure helpers) from mission runtime code.

Capabilities
------------
- Start a process with optional stdin/stdout file redirection.
- Read incremental stdout lines when output is piped.
- Send input to interactive subprocesses.
- Wait for process termination or for regex-matched output.
- Perform explicit async cleanup (`aclose`) to avoid deferred transport leaks.

Operational notes
-----------------
- `wait_until_output` only works when stdout is not redirected to a file.
- `send_input` raises `RuntimeError` if stdin is unavailable.
- `aclose` should be used on shutdown to reap pending subprocess resources,
  especially in tests.

