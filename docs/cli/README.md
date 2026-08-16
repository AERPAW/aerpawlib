## Overview

The `aerpawlib` CLI connects to a vehicle, loads your runner script, and executes the mission. Use `aerpawlib-run-proxy` for multi-vehicle ZMQ coordination.

## When to use this

Run any experiment script after `pip install -e .`. Pass `--script`, `--conn`, and `--vehicle` at minimum.

## Common workflow

```bash
aerpawlib \
  --api-version v2 \
  --script my_experiment.py \
  --vehicle drone \
  --conn udpin://127.0.0.1:14550 \
  --no-aerpaw-environment
```

For SITL locally, start ArduPilot SITL first (see repository README).

## Key concepts

### Execution flow

1. Resolve paths (`--script`, `--config`, `--log-file`, `--structured-log`) from your current working directory
1. Insert the repository root on `sys.path` (the process does **not** `chdir`; relative plan/KML paths follow your current working directory)
1. Merge JSON config files (`--config` may be repeated; later files override)
1. Import `aerpawlib.v1` or `aerpawlib.v2` and load your script
1. Find exactly one direct subclass of `Runner`, `BasicRunner`, `StateMachine`, or `ZmqStateMachine`
1. Forward unrecognized argv to `runner.initialize_args(...)`

### Required flags

| Flag | Description |
|------|-------------|
| `--script` | Python file (`.py` or path) or dotted module name |
| `--conn` | MAVSDK connection string |
| `--vehicle` | `drone`, `rover`, `none` (DummyVehicle), or `generic` |

### API and environment

| Flag | Default | Description |
|------|---------|-------------|
| `--api-version` | `v1` | `v1` or `v2` |
| `--no-aerpaw-environment` | off | Skip AERPAW platform connection (use for SITL) |

### Execution control

| Flag | Description |
|------|-------------|
| `--skip-init` | Skip vehicle initialize/armable checks |
| `--skip-rtl` | Do not auto RTL/RTH if still armed at end |
| `--conn-timeout` | Initial connection wait (seconds) |
| `--heartbeat-timeout` | Heartbeat loss threshold |
| `--mavsdk-port` | gRPC port per vehicle instance |

### ZMQ (multi-vehicle)

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
| `--safety-checker-ip` | Server host (default `127.0.0.1`) |

On AERPAW the process exits if the server is unreachable. When a client is attached, takeoff/goto/land/speed commands are validated before they are sent.

### Production (C-VM)

1. Start `aerpawlib-run-proxy` (opens TCP **5570 and 5571** on all interfaces; use `--in-port` / `--out-port` / `--bind` if needed).
2. Start `aerpawlib-safety-checker --port 14580 --vehicle_config <yaml>`.
3. Give every vehicle a unique `--mavsdk-port` and `--zmq-identifier`.
4. Point `--zmq-proxy-server` at the proxy host (not only `127.0.0.1` unless all runners share that host).
5. `--skip-rtl` is the only way to leave a vehicle armed after Ctrl-C, a runner exception, or heartbeat loss. If the link is already down, the last GUIDED setpoint remains on the autopilot.

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
aerpawlib --config sitl-drone.json --script my_experiment.py
```

CLI flags override config file values.

## See also

- `aerpawlib.v2` / `aerpawlib.v1`: runner and vehicle APIs
- `aerpawlib.cli.log`: logging components
- `examples/`: sample scripts and config files
