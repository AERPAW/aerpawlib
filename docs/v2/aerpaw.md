## Overview

This module is the v2 version of ``aerpawlib.v1.aerpaw``. It is significantly simpler than the v1 module.


It focuses on:
- reachability to the AERPAW forward server
- OEO (Operations and Experimentation Orchestrator) message forwarding
- local severity logging when the testbed is unavailable.

This module is used by the CLI; and should not be imported by mission code.

### Primary symbols
- `AERPAW_Platform` — lazy singleton. Probes the forward server on first use, tracks whether the process is in an AERPAW environment, and can suppress stdout for log routing.
- `log_to_oeo` / `log_to_oeo_async` — send human-readable lines to the OEO forward path; async variant uses `aiohttp` for non-blocking posts from the asyncio loop.
- OEO severity constants: `OEO_MSG_SEV_INFO`, `OEO_MSG_SEV_WARN`, `OEO_MSG_SEV_ERR`, `OEO_MSG_SEV_CRIT`.

### Behavior notes
- If the forward server is unreachable, the singleton still works for local logging. OEO network sends are simply skipped.
- Default forward host and port come from `aerpawlib.v2.constants` (`DEFAULT_FORWARD_SERVER_IP` / `DEFAULT_FORWARD_SERVER_PORT`).
