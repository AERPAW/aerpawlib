# aerpawlib Development Guide

For contributors working on the library, tests, and tooling. End-user workflows live in [USER_GUIDE.md](USER_GUIDE.md).

## Repository layout

```
aerpawlib/                 # Installable package
  __main__.py              # `aerpawlib` CLI: API version, script runner, config JSON
  structured_log.py        # JSON Lines StructuredEventLogger (v1 + v2)
  log.py                   # Shared ColoredFormatter, LogComponent
  constants.py             # Shared defaults (ports, timeouts, …)
  v1/                      # v1 API (stable): MAVSDK, DroneKit-style surface
    vehicles/              # core_vehicle.Vehicle, Drone, Rover
    runner.py              # Runner, BasicRunner, StateMachine, ZmqStateMachine
    safety.py              # SafetyCheckerServer / Client (v1 geofence flow)
    …
  v2/                      # v2 API: async-first, single event loop
    vehicle/               # base.Vehicle, Drone, Rover, state, VehicleTask
    safety/                # validation, SafetyCheckerClient, connection handler
    runner.py              # BasicRunner, StateMachine, descriptors
    …
scripts/                   # setup_sitl, run_example, …
tests/
  unit/                    # Fast tests, no SITL (v1 + v2 + CLI helpers)
  integration/             # SITL + real MAVSDK (v1 + v2)
  conftest.py              # Markers, SITL lifecycle, fixtures
docs/                      # This tree
examples/                  # v1 and v2 sample missions
.github/workflows/         # CI (unit tests)
```

Legacy shim: `aerpawlib.runner` re-exports v1 with a `DeprecationWarning`. Top-level `import aerpawlib` lazy-loads **v1** symbols for old scripts; new code should use `aerpawlib.v1` or `aerpawlib.v2` explicitly.

## Two APIs

| | **v1** (`--api-version v1`, default) | **v2** (`--api-version v2`) |
|---|--------------------------------------|-----------------------------|
| Concurrency | Background thread + dedicated asyncio loop for MAVSDK; main thread uses `asyncio` for user code | Single asyncio loop; telemetry and commands on the same loop |
| State | `ThreadSafeValue` + polling in `core_vehicle` | Plain `VehicleState` updated from async telemetry generators |
| Vehicles | `aerpawlib.v1.vehicles` (`Vehicle`, `Drone`, `Rover`, `DummyVehicle`) | `aerpawlib.v2` (`Drone.connect`, `Rover.connect`, …) |
| Runners | `BasicRunner`, `StateMachine`, `ZmqStateMachine` | v2 `runner.py` with config dataclasses / decorators |

See [v1/compromises.md](v1/compromises.md) for v1 design tradeoffs and [v2/README.md](v2/README.md) for v2 usage.

### v1: dual-loop / thread bridge

- Telemetry and MAVSDK run on a **background thread** with its own event loop.
- User `async` code runs on the **main** loop; MAVSDK coroutines are scheduled with `_run_on_mavsdk_loop()` (`asyncio.run_coroutine_threadsafe`).
- Always call `vehicle.close()` to stop the background loop and cancel tasks.

### v2: single-loop async

- `await Drone.connect(...)` wires MAVSDK `System` and starts telemetry tasks on the **current** loop.
- No `ThreadSafeValue`; subscriptions update `VehicleState` directly.
- Connection loss and heartbeats use `aerpawlib.v2.safety.connection` (`ConnectionHandler`) when available.

## CLI entry point

`aerpawlib` is defined in [pyproject.toml](../pyproject.toml) as `aerpawlib.__main__:main`.

Notable flags: `--api-version`, `--config` (JSON defaults; `null` values omit flags), `--structured-log FILE` (JSONL for v1 and v2), `--vehicle`, `--conn`, v2-only `--safety-checker-port`, logging `-v` / `-q`, `--log-file`.

## Testing

Install dev deps and (for integration tests) SITL tooling:

```bash
pip install -e .[dev]
# Integration tests only:
aerpawlib-setup-sitl
# or: ./scripts/install_dev.sh
```

### Unit tests (no vehicle / no SITL)

```bash
pytest tests/unit/ -v
# or
pytest -m unit -v
```

Rough coverage by file:

- **v1:** `test_v1_util`, `test_v1_helpers`, `test_v1_exceptions`, `test_v1_runner`, `test_v1_external`, `test_v1_safety`, `test_v1_vehicle`
- **v2:** `test_v2_types`, `test_v2_exceptions`, `test_v2_runner`, `test_v2_geofence`, `test_v2_plan`, `test_v2_testing`
- **Shared / CLI:** `test_main_runner_discovery`

### Integration tests (ArduPilot SITL)

Pytest can start and tear down SITL (separate instances for copter vs rover, distinct UDP ports). Details: [tests/README.md](../tests/README.md).

```bash
pytest tests/integration/ -v
# or
pytest -m integration -v
```

**External SITL** (you start `sim_vehicle.py` yourself):

```bash
pytest tests/integration/ -v --no-sitl
```

Layout includes both **v1** (`test_v1_drone`, `test_v1_rover`, …) and **v2** (`test_v2_drone`, `test_v2_velocity`, `test_v2_safety`, …) modules.

### Continuous integration

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs `pytest tests/unit/` on push/PR (Python 3.11 and 3.12). Integration tests are not run in CI by default (heavy SITL dependency).

## Code conventions

### Python version

- **Supported:** 3.9+ per `requires-python` in [pyproject.toml](../pyproject.toml).
- Prefer `Optional[X]` / `Union[X, Y]` where needed for 3.9; avoid `X | Y` in shared code if you must stay 3.9-clean (project also supports newer Pythons).

### Style

- Follow **PEP 8** and match surrounding modules. There is **no** Black/ruff config in `pyproject.toml`; do not assume a fixed line length beyond readability.

### Imports

- Prefer explicit versioned imports: `from aerpawlib.v1 import …`, `from aerpawlib.v2 import …`.
- `aerpawlib.v1.__init__` re-exports many symbols for a flat API; v2 is typically imported from submodules.

### Logging

- Use `get_logger(LogComponent.X)` from `aerpawlib.log` (or `aerpawlib.v1.log` / `aerpawlib.v2.log` as used locally).
- Components include `VEHICLE`, `DRONE`, `ROVER`, `RUNNER`, `SAFETY`, `SITL`, etc.

### Exceptions

- Raise or wrap with the hierarchy under `AerpawlibError` / version-specific modules; use `original_error=e` when wrapping lower-level failures.

## Adding features

### v1 – new method on `Drone` / `Rover`

1. Implement in `aerpawlib/v1/vehicles/drone.py` or `rover.py` (or `core_vehicle.py` if shared).
2. MAVSDK: `await self._run_on_mavsdk_loop(coro)`.
3. For blocking flows, update `_ready_to_move` as existing methods do.
4. Add or extend tests in `tests/integration/test_v1_*.py` when behavior needs a real stack; unit tests when logic is isolated.

### v2 – new method on `Drone` / `Rover`

1. Implement in `aerpawlib/v2/vehicle/drone.py` or `rover.py` (shared pieces in `base.py`).
2. Use `await` on MAVSDK directly; respect offboard / `VehicleTask` patterns already in the file.
3. Tests: `tests/unit/test_v2_*.py` and/or `tests/integration/test_v2_*.py`.

### New runner decorator (v1)

1. `aerpawlib/v1/runner.py`: decorator + wiring in `StateMachine._build()` (or relevant runner).
2. `tests/unit/test_v1_runner.py`.

### Safety checker (v1)

1. Constants in `aerpawlib/v1/constants.py` if needed.
2. Server/client in `SafetyCheckerServer` / `SafetyCheckerClient`.
3. [v1/safety_checker.md](v1/safety_checker.md).

### Safety / validation (v2)

See [v2/safety.md](v2/safety.md) and `aerpawlib/v2/safety/`.

## Debugging

### Structured JSONL

```bash
aerpawlib --api-version v2 --script my_mission.py --conn udpin://127.0.0.1:14550 --vehicle drone \
  --structured-log mission.jsonl
```

Same `--structured-log` works for v1. Events include `telemetry` (throttled), `mission_start` / `mission_end`, commands (`set_velocity`, …), and more; see [v2/README.md](v2/README.md).

### Console log level (`aerpawlib` CLI)

| Flags | Root log level |
|-------|----------------|
| *(none)* | INFO |
| `-v` / `--verbose` | DEBUG |
| `-q` / `--quiet` | WARNING |

Optional `--log-file PATH` adds a file handler at **DEBUG** regardless of console level.

There is **no** separate `--debug` flag on the CLI—use `-v`.

### Integration / SITL

```bash
SITL_VERBOSE=1 pytest tests/integration/ -v
```

Other env vars: see [tests/README.md](../tests/README.md) (`SIM_SPEEDUP`, `ARDUPILOT_HOME`, …).

### gRPC fork warning

When using `ExternalProcess` with `fork`:

```
Other threads are currently calling into gRPC, skipping fork() handlers
```

Setting `GRPC_ENABLE_FORK_SUPPORT=false` suppresses the message (cosmetic only).

## Release checklist

- [ ] `pytest tests/unit/ -v` (and integration locally if you touched vehicle/SITL paths)
- [ ] Bump version in [pyproject.toml](../pyproject.toml)
- [ ] Update [ROADMAP.md](ROADMAP.md) if scope changed
- [ ] Skim [USER_GUIDE.md](USER_GUIDE.md) / [docs/README.md](README.md) for stale flags or examples

## Related documentation

- [User Guide](USER_GUIDE.md) – How to run missions and use the platform
- [Documentation index](README.md) – All guides and API refs
- [v1 README](v1/README.md) – v1 API reference
- [v2 README](v2/README.md) – v2 API reference
- [v1 compromises](v1/compromises.md) – v1 architecture tradeoffs
- [v1 Safety Checker](v1/safety_checker.md) – v1 geofence / server
- [v2 Safety](v2/safety.md) – v2 validation and clients
- [Roadmap](ROADMAP.md) – Planned work
