# aerpawlib CLI guide

This document describes the `aerpawlib` command-line interface: how to run mission scripts, how configuration is resolved, and what each flag does in practice.

## How to invoke the CLI

After installing the package (for example with `pip install -e .`), the entry point is:

```bash
aerpawlib --help
```

You can also run the module directly, although there is no benefit to doing so:

```bash
python -m aerpawlib --help
```

## What happens when you start the CLI

1. File paths you pass on the command line (`--script`, `--config`, `--log-file`, `--structured-log`) are first resolved relative to the directory from which you launched the process (the shell’s current working directory at invocation time), not relative to the repository root.

2. The CLI then `chdir`s to the repository root. The project root is prepended to `sys.path` so imports and examples behave consistently.

3. If you passed `--config`, JSON files are merged into synthetic argv *before* the main parser runs; see [Configuration files](#configuration-files).

4. The chosen API module (`aerpawlib.v1` or `aerpawlib.v2`) is imported, then your experimenter script is loaded.

5. Exactly one user-defined runner class must be found in the script (subclass of the framework `Runner` / `StateMachine` / `BasicRunner` / `ZmqStateMachine`, with **direct** inheritance from one of those base classes; deeper inheritance chains are not supported). See `aerpawlib.cli.discovery` for rules.

6. Any tokens the main parser does not recognize are kept as unknown arguments and passed to `runner.initialize_args(...)` so your runner can define its own options.

## Minimal example

```bash
aerpawlib \
  --script examples/v2/basic_example.py \
  --conn udpin://127.0.0.1:14550 \
  --vehicle drone \
  --api-version v2 \
  --no-aerpaw-environment
```

For real hardware, replace `--conn` with a serial device or other MAVSDK connection string your setup uses.

---

## Configuration files (`--config`)

- You may pass `--config path1.json --config path2.json` multiple times.
- Later files override keys from earlier files.
- Each file must be a single JSON **object** whose keys correspond to CLI long options (with hyphens), e.g. `api-version`, `conn`, `vehicle`, `no-aerpaw-environment`.
- A key mapped to JSON `null` removes that key from the merged result (so no flag is emitted for it).
- Types:
  - Boolean `true`: Emits the flag alone (for store-true style options).
  - Boolean `false` or `null`: Omits the flag (for booleans, `false` does not emit `--flag`).
  - Scalars: Emits `--key` and the stringified value as the next argv token.
  - Arrays: Emits `--key` once per element, each followed by one value (for options that can be repeated).
After merge, real command-line arguments still present in argv override the merged config, because merged flags are prepended before the remainder of argv.

Example `sitl-drone.json`:

```json
{
  "api-version": "v2",
  "vehicle": "drone",
  "no-aerpaw-environment": true,
  "conn": "udpin://127.0.0.1:14550"
}
```


Usage:

```bash
aerpawlib --config sitl-drone.json --script examples/v2/basic_example.py ...
```

---

## Core arguments

### `--script`

*Note*: Required  unless `--run-proxy` is used.

- If the value contains a path separator or ends with `.py`, it is treated as a file. Relative paths are resolved against the invocation directory, then (if still not found) against the repo root for convenience.
- If there is no path separator and no `.py` suffix, the value is passed to `importlib.import_module` (dotted module name).

### `--conn` / `--connection`

*Note*: Required unless `--run-proxy` is used.

MAVSDK-style connection string (for example `udpin://127.0.0.1:14550`, `serial:///dev/ttyUSB0:57600`). The CLI passes this through to vehicle construction / `connect()`.

### `--vehicle`

*Note*: Required  unless `--run-proxy` is used.

Allowed values:

| Value     | Meaning                                                       |
|-----------|---------------------------------------------------------------|
| `generic` | Generic `Vehicle` class (Deprecated in favor of `none`)       |
| `drone`   | `Drone`                                                       |
| `rover`   | `Rover`                                                       |
| `none`    | `DummyVehicle` (no real vehicle; useful for dry runs / tests) |

### `--api-version`

- Either `v1` or `v2`
- Default: `v1`
- Selects which top-level package is imported (`aerpawlib.v1` vs `aerpawlib.v2`) and therefore a different API.
- See ``aerpawlib.v1`` and ``aerpawlib.v2`` documentation for more information.

*Note*: In the future, the API version will be automatically detected based on the script’s imports, but for now you must specify it explicitly. If you choose the wrong version, the CLI may fail to find a runner or raise import errors.

---

## Execution flags

### `--skip-init`

- When **not** passed (default), if the vehicle implements `_preflight_wait`, the CLI calls it before the runner’s main work. That routine waits for armable / health conditions (with timeouts) and records whether the mission should proceed toward arming (`_will_arm` / related state).
- When passed: Skips that `_preflight_wait` call entirely. This will likely prevent the vehicle from arming unless the vehicle is already in an armable state at connection time.

### `--skip-rtl`

By default, if the experiment ends with the vehicle still **armed** and the disconnect path was not a “heartbeat lost” style failure, the CLI attempts return-to-launch (`drone`) or navigate to stored home (`rover` with `home_coords`). With `--skip-rtl`, that automatic RTL / home navigation is disabled.

### `--no-aerpawlib-stdout`

Passed into `AERPAW_Platform` to reduce platform-side printing to stdout where that flag is honored. Does not disable Python logging handlers configured by the CLI itself.

### `--no-aerpaw-environment`

Skips mandatory platform connection. When not passed, failing to connect to the AERPAW environment will simply stop execution of the script.

---

## ZMQ proxy (`--run-proxy` and related)

### `--run-proxy`

- Starts the bundled ZMQ **XSUB/XPUB forwarder** for multi-process / multi-runner messaging (`run_zmq_proxy` in the active API package). This mode **does not** run a script; `--script`, `--conn`, and `--vehicle` are **not** required.
- The proxy runs until interrupted; bind addresses use fixed ports **5570** (in) and **5571** (out) on all interfaces (`tcp://*:5570` / `tcp://*:5571`). If those ports are in use, startup fails.
- API version is honored so v1 vs v2 logging/constants apply, but both versions use the same port numbers today.

### `--zmq-identifier`

Used when your discovered runner is a **`ZmqStateMachine`** subclass. Must be provided together with `--zmq-proxy-server`; otherwise the CLI errors. The value identifies this runner instance to the proxy mesh (for example `leader` / `follower` patterns in examples).

### `--zmq-proxy-server`

Hostname or IP of the machine running `aerpawlib --run-proxy` (often `127.0.0.1`). Used with `--zmq-identifier` to configure ZMQ bindings on the runner.

An example of how these three flags would be used:

```bash
# Terminal A
aerpawlib --run-proxy --api-version v2

# Terminal B (example; your script and flags will differ)
aerpawlib --script ... --conn ... --vehicle drone \
  --zmq-identifier leader --zmq-proxy-server 127.0.0.1
```

---

## Logging

### `-v` / `--verbose`

- Sets the root logger level to DEBUG on the console handler.
- If both `-v` and `-q` are given, verbose wins.

### `-q` / `--quiet`

- Sets the console level to WARNING.
- Loses to `-v`

### `--log-file PATH`

- Adds a file logging handler to the root logger
- The file handler is fixed at DEBUG level so file logs are more detailed than the default console INFO level, even without `-v`.
- `PATH` is resolved relative to the invocation directory (then absolute/normalized).

### `--structured-log FILE`

- When set, opens JSONL structured event logging (`StructuredEventLogger`) for mission lifecycle and related events (v1 and v2). If the file already exists, a warning is logged and the file is **overwritten**.
- v1: Attached to the vehicle; logs `mission_start` / `mission_end` (and similar) around the run.
- v2: Attached to both vehicle and runner; also logs connection-loss style events when applicable.

Omit this flag entirely to disable structured logging.

---

## Connection tuning

### `--conn-timeout` / `--connection-timeout`

Caps how long the CLI waits for the initial vehicle connection. Also influences internal “connected” polling where applicable.

### `--heartbeat-timeout`

Maximum time the vehicle may appear disconnected (or without heartbeat progress, depending on API) before the disconnect watcher treats the situation as fatal and tears down the experiment.

### `--mavsdk-port`

gRPC port for the embedded mavsdk_server process. Use a unique port per concurrent vehicle on one host to avoid conflicts.

### `--safety-checker-port` (v2)

- When running inside a connected AERPAW environment, if you omit the flag, the client defaults to port 14580 and must reach a real `SafetyCheckerServer`. Failure to connect ends the experiment.
- When not in AERPAW (standalone), if you omit the flag, a no-op safety checker is used (all checks pass; message logged).
- If you set an explicit port and connection fails in standalone, the library falls back to the no-op checker with an error log. In AERPAW mode, explicit or default port connection failure remains fatal.
