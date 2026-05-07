## Overview

This module provides the v2 AERPAW platform helper used by the runtime and CLI plumbing.

It focuses on:
- reachability checks against the AERPAW forward server
- OEO (Operations and Experimentation Orchestrator) message forwarding
- checkpoint read/write helpers
- custom OEO topic publishing

This module is used by the CLI and vehicle internals; mission code normally interacts with it through `aerpawlib.v2.vehicle`.

### Primary symbols
- `AerpawPlatform`: connection-aware helper that probes the forward server during initialization and caches `is_connected`.
- `OeoSeverity`: severity enum for OEO console messages (`INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- `log_to_oeo` / `log_to_oeo_async`: send human-readable lines to the OEO forward path; the async variant uses `aiohttp`.
- `checkpoint_*` methods: manage boolean, integer, and string checkpoint values.
- `publish_user_oeo_topic` / `publish_user_oeo_topic_async`: publish base64-encoded topic/value payloads to the OEO bridge.

### Behavior notes
- `AerpawPlatform.__init__()` checks `/ping` once and stores the result in `is_connected`.
- If the forward server is unavailable, local logging still works, but checkpoint helpers raise and OEO network sends are skipped.
- `suppress_stdout=True` disables local logger output and the offline warning.
- Default forward host and port come from `aerpawlib.v2.constants` (`DEFAULT_FORWARD_SERVER_IP` / `DEFAULT_FORWARD_SERVER_PORT`).
