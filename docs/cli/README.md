## Overview

The `aerpawlib` CLI connects to a vehicle, loads your runner script, and executes the mission. Use `aerpawlib-run-proxy` for multi-vehicle ZMQ coordination.

## When to use this

Run any experiment script after `pip install .`. Pass `--script`, `--conn`, and `--vehicle` at minimum (`--conn` is optional with `--vehicle none`).

## Common workflow

```bash
aerpawlib \
  --api-version v2 \
  --script my_experiment.py \
  --vehicle drone \
  --conn udpin://127.0.0.1:14550 \
  --no-aerpaw-environment
```

`--no-aerpaw-environment` is required for local SITL. Prefer MAVSDK `udpin://host:port`; `udp:host:port` and `udp://host:port` are rewritten automatically.

## Key concepts

### How a run is assembled

1. Paths (`--script`, `--config`, `--log-file`, `--structured-log`) are resolved from your current working directory. Relative plan and KML paths also use that directory.
1. Repeated `--config` files merge; later files override earlier ones. CLI flags override config files.
1. Your script must define exactly one runner class (`BasicRunner`, `StateMachine`, or `ZmqStateMachine`).
1. Extra arguments after the known flags are passed unchanged to `runner.initialize_args(...)`. That includes helper-style underscore flags such as `--safety_checker_ip`.

### Required flags

| Flag | Description |
|------|-------------|
| `--script` | Python file (`.py` or path) or dotted module name |
| `--conn` / `--connection` | MAVSDK connection string (required unless `--vehicle none`) |
| `--vehicle` | `drone`, `rover`, `none` (DummyVehicle), or `generic` |

### API and environment

| Flag | Default | Description |
|------|---------|-------------|
| `--api-version` | inferred from the script | `v1` or `v2`; omit to detect from the Runner class |
| `--no-aerpaw-environment` | off | Skip AERPAW platform connection (required for SITL; refused on a live E-VM if the OEO forwarder is reachable) |

### Execution control

| Flag | Default | Description |
|------|---------|-------------|
| `--skip-init` | off | Skip vehicle initialize/armable checks |
| `--skip-rtl` | off | Do not auto RTL/RTH at successful end if still armed |
| `--conn-timeout` / `--connection-timeout` | 30 s | Initial connection wait |
| `--heartbeat-timeout` | 5 s | Heartbeat loss threshold |
| `--mavsdk-port` | 50051 | gRPC port per vehicle instance |
| `--config` | — | JSON preset(s); may be repeated |

Without `--skip-rtl`, an armed drone RTLs after a successful run. An armed rover goes to `home_coords` if known. Ctrl-C, a script error, or a lost link leave the last GUIDED setpoint.

### ZMQ (multi-vehicle)

| Flag | Description |
|------|-------------|
| `--zmq-identifier` | Unique runner id (for example `leader`) |
| `--zmq-proxy-server` | Proxy host (for example `127.0.0.1`) |

```bash
aerpawlib-run-proxy   # terminal 1
aerpawlib --zmq-identifier leader --zmq-proxy-server 127.0.0.1 ...  # terminal 2+
```

### Logging

| Flag | Description |
|------|-------------|
| `-v` / `--verbose` | DEBUG console logging |
| `-q` / `--quiet` | WARNING and above only |
| `--log-file PATH` | DEBUG log file |
| `--structured-log FILE` | JSONL mission/telemetry events |
| `--no-aerpawlib-stdout` | Mute aerpawlib console output |
| `--no-status-bar` | Hide the live mission status bar (spinner and telemetry) |

### Safety (v1 and v2)

| Flag | Description |
|------|-------------|
| `--safety-checker-port` | SafetyCheckerServer port (default 14580 on AERPAW) |
| `--safety-checker-ip` | Server host. On AERPAW this defaults to this node's C-VM XV (`AP_EXPENV_CVM_<n>_XV`, typically `192.168.32.25`). Outside AERPAW it defaults to `127.0.0.1` when a port or IP is given. |

On AERPAW the process exits if the server is unreachable. Unmatched args (including helper `--safety_checker_ip` / `--safety_checker_port`) are passed through to the script; the library also uses those extra args when attaching the client. When a client is attached, takeoff/goto/land/speed commands are validated before they are sent.

### Production (C-VM)

1. Start `aerpawlib-run-proxy` (default ports 5570 and 5571). Use `--in-port` / `--out-port` / `--bind` only if you need different ports or a bind address.
2. Start `aerpawlib-safety-checker --port 14580 --vehicle_config <yaml>`.
3. Give every vehicle a unique `--mavsdk-port` and `--zmq-identifier`.
4. Point `--zmq-proxy-server` at the host running the proxy (use `127.0.0.1` only when every runner is on that same host).
5. Without `--skip-rtl`, an armed vehicle returns home only after a successful run. Ctrl-C, a script error, or a lost link leave the last GUIDED setpoint.

### Config files

JSON object with keys matching CLI long options (hyphenated):

```json
{
  "api-version": "v2",
  "vehicle": "drone",
  "no-aerpaw-environment": true,
  "conn": "udpin://127.0.0.1:14550"
}
```

```bash
aerpawlib --config configs/sitl-drone.json --script my_experiment.py
```

CLI flags override config file values.

## See also

- `aerpawlib.v2` / `aerpawlib.v1`: runner and vehicle APIs
- `aerpawlib.cli.log`: logging components
- `examples/`: sample scripts and config files
