## Overview

ZMQ proxy helpers for v1 distributed runner workflows.

This module contains low-level functions used with `ZmqStateMachine`:

- `check_zmq_proxy_reachable(proxy_addr, timeout_s=...)`
  - Performs a fast TCP probe against the proxy subscriber port.
- `run_zmq_proxy()`
  - Starts a blocking XSUB/XPUB proxy device bound to configured ports.

Operational notes
-----------------
- The proxy is synchronous and blocking by design in v1.
- Start the proxy before launching ZMQ-enabled runners.
- Port values and timeout defaults come from `aerpawlib.v1.constants`.

