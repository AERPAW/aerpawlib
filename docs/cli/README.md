# aerpawlib CLI Guide

The `aerpawlib` CLI orchestrates MAVSDK vehicle connections and experiment runner scripts. Additionally, the ZMQ proxy server can be run via a dedicated utility command. This guide details how to invoke these CLI commands, configure executions, and utilize available flags.

## Invocation

After installing the package (for example, via `pip install -e .`), use the `aerpawlib` command as the primary entry point to run scripts, or `aerpawlib-run-proxy` to start the ZMQ broker.

```bash
# View help for the script runner
aerpawlib --help

# View help for the ZMQ proxy server
aerpawlib-run-proxy --help
```

## Initialization and Execution Flow

When you launch the CLI, the system executes the following sequence.

1. The CLI resolves command-line paths (`--script`, `--config`, `--log-file`, `--structured-log`) relative to your current working directory, not the repository root.
2. The process changes the working directory (`chdir`) to the repository root and prepends it to `sys.path` to guarantee consistent imports.
3. The system loads and merges JSON configuration files before the main parser executes.
4. The CLI imports the specified API module (`aerpawlib.v1` or `aerpawlib.v2`) and loads your target experimenter script.
5. The CLI scans the script for exactly one class inheriting **directly** from `Runner`, `StateMachine`, `BasicRunner`, or `ZmqStateMachine`. Deep inheritance chains are not supported.
6. Unrecognized arguments bypass the main parser and route directly to `runner.initialize_args(...)` for custom script-specific handling.

## Minimal Example

```bash
aerpawlib \
  --script examples/v2/basic_example.py \
  --conn udpin://127.0.0.1:14550 \
  --vehicle drone \
  --api-version v2 \
  --no-aerpaw-environment
```

For hardware deployments, replace the `--conn` argument with the appropriate serial device or MAVSDK connection string.

---

## Configuration Files

You can layer settings by passing the `--config` flag multiple times. Subsequent files override keys from earlier ones, while explicit command-line flags take the highest precedence and override all file-based settings.

Configuration files must be a single JSON object where the keys match CLI long options (using hyphens).

| JSON Value                | CLI Behavior                                                      |
|:--------------------------|:------------------------------------------------------------------|
| `true`                    | Activates boolean flags (e.g., emits `--flag`).                   |
| `false` or `null`         | Omits the flag completely.                                        |
| Scalar (String or Number) | Emits `--key value` as the next argv token.                       |
| Array                     | Generates repeated flags (e.g., emits `--key item1 --key item2`). |

Example configuration file `sitl-drone.json`

```json
{
  "api-version": "v2",
  "vehicle": "drone",
  "no-aerpaw-environment": true,
  "conn": "udpin://127.0.0.1:14550"
}
```

To run the CLI with this configuration, use the following command.

```bash
aerpawlib --config sitl-drone.json --script examples/v2/basic_example.py
```

---

## Core Arguments

### `--script`
This flag is required. The CLI treats values containing a path separator or a `.py` extension as files. These are resolved locally first, then against the repository root. Values without separators are treated and imported as dotted Python modules.

### `--conn` / `--connection`
This flag is required. It defines the MAVSDK connection string used for vehicle communication (e.g., `udpin://127.0.0.1:14550` or `serial:///dev/ttyUSB0:57600`).

### `--vehicle`
This flag is required. It specifies the vehicle type for the experiment.

| Value     | Target                                          |
|:----------|:------------------------------------------------|
| `drone`   | `Drone`                                         |
| `rover`   | `Rover`                                         |
| `none`    | `DummyVehicle` (ideal for dry runs and testing) |
| `generic` | `Vehicle` (deprecated, shouldn't use)           |

### `--api-version`
Selects either the `aerpawlib.v1` or `aerpawlib.v2` package. It defaults to `v1`. Selecting a version incompatible with your script's imports will trigger discovery or runtime errors.

---

## Execution Control

### `--skip-init`
The CLI normally calls `initialize` to ensure the vehicle is armable and healthy before the runner starts. This flag bypasses those checks. The vehicle may fail to arm if it is not ready at connection time.

### `--skip-rtl`
The CLI automatically attempts a Return-To-Launch (drones) or Return-to-Home (rovers) if the script finishes while the vehicle is still armed. This flag disables that automatic navigation.

### `--no-aerpawlib-stdout`
Instructs the `AERPAW_Platform` to suppress standard output printing. Python logging handlers configured by the CLI remain active.

### `--no-aerpaw-environment`
Bypasses the mandatory AERPAW platform connection. Without this flag, the script immediately terminates if it cannot establish a connection to the environment.

---

## ZMQ Orchestration

To support multi-vehicle state machine execution, you can run a central ZMQ proxy/broker.

### `aerpawlib-run-proxy`
This standalone command launches the ZMQ XSUB/XPUB message broker on fixed ports 5570 (inbound) and 5571 (outbound). Start this proxy in a separate terminal process before running any coordinate-sharing scripts.

```bash
aerpawlib-run-proxy
```

### `--zmq-identifier`
Identifies the specific runner instance (e.g., `leader`) to the proxy mesh. This is required for `ZmqStateMachine` runners and must be paired with `--zmq-proxy-server`.

### `--zmq-proxy-server`
Defines the hostname or IP address of the machine running the ZMQ proxy.

---

## Logging and Diagnostics

| Flag                    | Behavior                                                                                                                |
|:------------------------|:------------------------------------------------------------------------------------------------------------------------|
| `-v` / `--verbose`      | Sets the console root logger to the DEBUG level. Overrides quiet mode.                                                  |
| `-q` / `--quiet`        | Restricts the console logger to the WARNING level.                                                                      |
| `--log-file PATH`       | Redirects DEBUG-level logs to a specified file, resolved against the invocation directory.                              |
| `--structured-log FILE` | Enables JSONL-formatted event logging for mission lifecycles and connections. Overwrites the file if it already exists. |

---

## Connection Tuning

### `--conn-timeout` / `--connection-timeout`
Sets the maximum duration the CLI will wait for the initial vehicle connection handshake.

### `--heartbeat-timeout`
Defines the grace period for missing heartbeats before the disconnect watcher considers the connection lost and tears down the experiment.

### `--mavsdk-port`
Specifies the gRPC port for the embedded `mavsdk_server` process. Assign a unique port per concurrent vehicle on a single host to prevent conflicts.

### `--safety-checker-port` (v2)
Controls the port interface for the `SafetyCheckerServer`. In a connected AERPAW environment, it defaults to port 14580, and failure to connect ends the experiment. In standalone mode, it defaults to a no-op checker that automatically passes all checks.

### `--safety-checker-ip` (v2)
Controls the IP/host address interface for the `SafetyCheckerServer`. Defaults to `127.0.0.1`.