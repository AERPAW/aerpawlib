# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.4.8] (2026-08-31)

### Summary

AERPAW testbed compatibility for **v1 and v2** after virtual experiment 1456. Safety-checker host, ping detection, copter mode/heading, v2 runner robustness, and examples now match E-VM policy (GUIDED/LAND only, `min_alt` 20, land within 5 m of takeoff). CLI `--api-version` still defaults to **v1**.

### Fixed

- **Safety-checker default host.** AERPAW default is this node's C-VM XV (`AP_EXPENV_CVM_${N}_XV`, typically `192.168.32.25`), not the OEO Console (`AP_EXPENV_OEOCVM_XM`). `--safety-checker-ip` still overrides.
- **AERPAW `/ping` status.** v1 and v2 treat only HTTP 2xx/3xx as connected. Probe `/ping/` first so live consoles that 400 `/ping` still detect the environment.
- **`action.hold()` on AERPAW.** Copter `action.hold()` is LOITER (mode 5) and severs the E-VM MAVLink link. Skip hold on AERPAW; send GUIDED (4) only. v2 no longer calls `_pre_auto_arm()` while waiting for the safety pilot.
- **`set_heading` stays in GUIDED.** Heading uses `MAV_CMD_CONDITION_YAW` instead of `offboard.start()`, which the copter filter does not allow.
- **v2 ground auto-disarm.** Copters that auto-disarm on the ground no longer raise `UnexpectedDisarmError` (fixes ZMQ leader/follower when the leader never takes off).
- **`VehicleTask.wait_done()` after `cancel()`.** User-requested cancel completes the handle; the caller checks `is_cancelled()`.
- **v2 disconnect OEO callback.** `log_to_oeo` accepts `str | OeoSeverity` so `severity="CRITICAL"` no longer raises `'str' object has no attribute 'value'`.
- **v2 MAVSDK UDP bind.** Occupied `udpin://` listen ports raise `PortInUseError` instead of attaching to a stale `mavsdk_server`.
- **Idle state-machine waits.** Identity transitions sleep 0.1 s and log at DEBUG instead of INFO at 100 Hz.
- **Examples / plans.** Takeoff 25 m, land at home, `orbit.plan` waypoint ≥ 25 m, figure-eight radius 10 m, `plan_example.py` honors `--file`, docstrings cite `.plan` files, ping/iperf launchers resolve under `/root` or `$HOME`.

### Changed

- CLI help still recommends v2 for new experiments; **`--api-version` default remains v1**.

## [1.4.7] (2026-08-25)

### Summary

Testbed compatibility fix for **v1 and v2**. The library-level safety checker now targets the C-VM in AERPAW, helper underscore flags still work, and auto RTL matches old aerpawlib (success only).

### Fixed

- **AERPAW safety-checker default host.** The library-level client no longer defaults to `127.0.0.1:14580` on the E-VM. In AERPAW it uses the C-VM address from `AP_EXPENV_OEOCVM_XM` (typically `192.168.32.25`), the same source as OEO.
- **Helper underscore safety flags.** Unmatched args such as `--safety_checker_ip` / `--safety_checker_port` still pass through to the script. The library-level client also reads those extra args, so helpers do not have to switch to dashed flags.

### Changed

- Auto RTL/RTH runs only after a successful mission (unless `--skip-rtl`). Ctrl-C, script errors, and heartbeat loss no longer command RTL; the last GUIDED setpoint remains. Examples use `--safety-checker-ip` / `--safety-checker-port` instead of extra-arg underscore forms.

## [1.4.6] (2026-08-16)

### Summary

Production-hardening release for **v1 and v2**. Multi-vehicle ZMQ is no longer fire-and-forget; safety checks run on the command path when a SafetyCheckerServer is attached; RTL runs on abort as well as success.

### Fixed

- **ZMQ multi-vehicle packet loss.** PUB/SUB now waits for `EVENT_CONNECTED`, HELLO is a presence heartbeat, `wait_for_peers()` is public, and `transition_runner` / `query_field` use ACK + retry + `req_id`. JSON control plane (no pickle). `@expose_zmq` aliases are honored; unknown transitions are ignored instead of crashing the machine. Proxy reachability checks **both** 5570 and 5571. `aerpawlib-run-proxy` accepts `--in-port`, `--out-port`, `--bind`.
- **Safety advertised but not enforced.** `takeoff` / `goto_coordinates` / `land` / `set_groundspeed` call `can_*` (v2) or the v1 SafetyCheckerClient when attached, and fail closed. v1 CLI accepts `--safety-checker-port` / `--safety-checker-ip`.
- v1 Ctrl-C now cancels the runner (the shutdown event is raced against the mission) so RTL can run.
- v2 Ctrl-C no longer `aclose()`s the vehicle in the signal handler, which had skipped RTL.
- v2 `takeoff` waits for armable/GPS, then validates, then arms — a vehicle still acquiring a fix no longer fail-closes before the arm wait.
- v1 `takeoff` validates safety before arming so a rejected takeoff does not RTL-on-failure while armed.
- Reliable ZMQ TRANSITION/FIELD_REQUEST retries ACK duplicates without re-running the handler. Reliable send retries catch `asyncio.TimeoutError` so Python 3.10 actually retries.
- Abort RTL flies home at the current altitude (not `home.alt ≈ 0`) so the waypoint `min_alt` check no longer rejects it; if the goto is still rejected, the vehicle lands in place.
- Landing validation no longer fails with “no takeoff location recorded” when takeoff was never validated.
- Takeoff climb and land-wait now time out on both APIs (default 300 s).
- DroneKit-style `udp:host:port` connection strings are remapped to `udpin://`.
- GUIDED-mode MAVLink commands use `AP_EXPENV_MAV_SYSID` / `MAV_SYSID` when set (no longer hardcoded `1` only).
- Preplanned-trajectory speed is applied **before** goto (removes the speed-change race).

### Changed

- RTL/RTH on Ctrl-C, runner failure, unexpected end, and heartbeat loss unless `--skip-rtl`. Last GUIDED setpoint remains if the link is already down.
- `dronekit` removed from install requires (unused after the MAVSDK migration).
- pytest / pdoc / MAVProxy moved to optional extras: `pip install -e ".[dev,sitl]"`.
- v2 re-exports `in_background` and `sleep` for v1 script ports.
- `configs/v2-drone.json` sets `mavsdk-port` 50051.

### Added

- `ZmqStateMachine.wait_for_peers(identifiers, timeout=30)` — call this before the first remote command.
- `aerpawlib-run-proxy` flags: `--in-port`, `--out-port`, `--bind`.

## [1.4.5] (2026-07-13)

Bugfix release on the way to general availability: CLI adds the script parent directory to `sys.path`; drones and rovers switch to GUIDED via MAVLink before arming; `set_groundspeed` uses `set_current_speed`; connection-string scheme checks are left to MAVSDK. See the [1.4.5 GitHub release](https://github.com/AERPAW/aerpawlib/releases/tag/1.4.5).

## [1.4.3] (2026-06-12)

### Summary

Stable release targeting **v1** as the production API for existing AERPAW experiment scripts. v1 preserves the surface of the original [DroneKit-based aerpawlib](https://github.com/morzack/aerpawlib-vehicle-control) while using MAVSDK internally.

### Added

- **v2 API** (`aerpawlib.v2`): async vehicle control, `can_takeoff` / `can_goto` / `can_land`, non-blocking `goto_coordinates` with `VehicleTask`, unexpected-disarm runner guard, and CLI safety-checker auto-wiring.
- Structured JSONL experiment logging via `--structured-log`.
- Layered CLI config presets under `configs/` (e.g. `v1-drone.json` + `sitl-drone.json`).
- Expanded unit test coverage for v1 and v2; CI runs unit tests on Python 3.10 to 3.14.

### Changed

- Vehicle driver stack migrated from DroneKit to **MAVSDK** (v1 keeps DroneKit-compatible telemetry wrappers in `aerpawlib.v1.vehicle.telemetry_compat`).
- CLI default remains `--api-version v1` for backward compatibility with existing scripts.
- Root-level imports (`from aerpawlib.vehicle import …`) still work but emit deprecation warnings; prefer `from aerpawlib.v1 import …`.

### Migration notes (DroneKit era → v1)

| Topic | Guidance |
|-------|----------|
| Imports | Use `aerpawlib.v1` (or legacy `aerpawlib.*` until removed). |
| Connection strings | Verify MAVSDK format for your setup (`udp:…` or `udpin://…`; see examples and `configs/sitl-*.json`). |
| Runner methods | Vehicle commands are `async`; use `await` in `@entrypoint` and `@state` methods. |
| `initialize()` | Still synchronous on v1; do not `await` it. |
| Direct `dronekit` usage | Review scripts that import DroneKit alongside aerpawlib; vehicle control goes through aerpawlib v1. |
| v2 | Optional for new scripts; not required for DroneKit-era parity. |

### Config presets (v1 production)

Layer vehicle type with environment-specific connection settings:

```bash
# SITL drone
aerpawlib --config configs/v1-drone.json --config configs/sitl-drone.json --script examples.v1.basic_runner

# SITL rover (separate MAVSDK port)
aerpawlib --config configs/v1-rover.json --config configs/sitl-rover.json --script examples.v1.basic_runner
```

[`configs/v1-drone.json`](configs/v1-drone.json) sets `mavsdk-port` 50051; [`configs/v1-rover.json`](configs/v1-rover.json) uses 50052 to avoid conflicts when both simulators run.

## [1.4.2] and earlier

See git history for prior releases. Notable milestones: documentation overhaul, status bar improvements, v2 lifecycle hardening, and initial dual-API (v1/v2) split.
