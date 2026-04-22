## Overview

v2’s `ZmqStateMachine` expects a running forwarder so publishers and subscribers can meet on fixed ports.

These helpers are what the CLI and other scripts use to verify the broker is up before a mission starts. They shouldn't be imported or used by experimenter code.

### Primary functions
- `check_zmq_proxy_reachable(proxy_addr, timeout_s=...)`:  TCP connect probe against the proxy’s subscriber-facing port (see `ZMQ_PROXY_OUT_PORT` in ``aerpawlib.v2.constants``).
- `run_zmq_proxy()`:  start the blocking `zmq.proxy` loop, binding the inbound and outbound ports that match `ZMQ_PROXY_IN_PORT` / `ZMQ_PROXY_OUT_PORT`.

### Behavior notes
- The proxy is synchronous and blocks the thread or process. It is run with `aerpawlib --run-proxy` (see CLI documentation)
- Port defaults and timeouts are stored in `aerpawlib.v2.constants`.
