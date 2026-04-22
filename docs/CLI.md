# to remove

# CLI Guide

The `aerpawlib` CLI runs mission scripts with either the v1 or v2 API.

## Basic usage

```bash
aerpawlib --script my_mission.py --conn udpin://127.0.0.1:14550 --vehicle drone
```

## Core options

| Option                    | Description                            |
|---------------------------|----------------------------------------|
| `--script`                | Script path or dotted module path      |
| `--conn` / `--connection` | MAVSDK connection string               |
| `--vehicle`               | `vehicle`, `drone`, `rover`, or `none` |
| `--api-version`           | `v1` (default) or `v2`                 |

## Configuration files

Use repeatable `--config` JSON files to define defaults.

```bash
aerpawlib --config configs/v1-drone.json --config configs/sitl-drone.json --script examples.v1.basic_runner
```

Later config files override earlier ones. Explicit CLI arguments override config values.

## Logging

| Option                  | Description                          |
|-------------------------|--------------------------------------|
| `-v`, `--verbose`       | DEBUG console logging                |
| `-q`, `--quiet`         | WARNING+ console logging             |
| `--log-file PATH`       | Write detailed logs to a file        |
| `--structured-log FILE` | Write JSONL mission/telemetry events |

## Connection and safety tuning

| Option                  | Description                                  |
|-------------------------|----------------------------------------------|
| `--conn-timeout`        | Initial connection timeout (seconds)         |
| `--heartbeat-timeout`   | Max heartbeat gap before disconnect handling |
| `--mavsdk-port`         | Embedded mavsdk_server gRPC port             |
| `--safety-checker-port` | v2 safety checker port                       |

## ZMQ mode

1. Start proxy: `aerpawlib --run-proxy`
2. Run scripts with `--zmq-identifier` and `--zmq-proxy-server`

## Run examples with managed SITL (beta)

```bash
aerpawlib-run-example --script examples/v2/basic_example.py --vehicle drone --api-version v2
```

This helper starts/stops SITL automatically around the script run.
