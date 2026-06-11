## Overview

AERPAW platform integration for v2: forward-server reachability, OEO logging, checkpoints, and topic publishing. Used by the CLI and vehicle internals.

## When to use this

Mission code typically interacts with the platform indirectly through the CLI and vehicle setup. Import when you need explicit OEO or checkpoint calls in advanced experiments.

## Key concepts

| Symbol | Description |
|--------|-------------|
| `AerpawPlatform` | Probes forward server; exposes `is_connected` |
| `OeoSeverity` | `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `log_to_oeo` / `log_to_oeo_async` | Send lines to OEO |
| `checkpoint_*` | Boolean, integer, string checkpoint values |
| `publish_user_oeo_topic` | Publish base64 topic payloads |

If the forward server is unavailable, local logging continues; network OEO sends are skipped.

## See also

- `aerpawlib.v1.aerpaw`: v1 platform helpers
- `aerpawlib.cli`: `--no-aerpaw-environment`
