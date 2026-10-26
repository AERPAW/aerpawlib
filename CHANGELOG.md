# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- **Off-pad land ended the session (v1, v2).** `land()` now raises `LandingError` without sending LAND when the drone is more than 4.5 m from where it took off, so the script can fly back while the drone keeps hovering in GUIDED. Before, the safety checker's 5 m landing check never ran: since 1.10.0 nothing recorded a takeoff location, so every land was sent, and the C-VM filter aborted any land more than 5 m from its pad. The drone records its pad at the first takeoff after arming and clears it once a land completes. `return_to_launch` now lands in place after a failed home goto only within the same 4.5 m.

## [1.13.0] (2026-10-24)

### Summary

After a safety pilot, failsafe, or the C-VM collision hold takes a vehicle out of GUIDED on the AERPAW testbed, scripts get `VehicleTakenOverError` instead of being cut off by the C-VM filter.

### Added

- **`VehicleTakenOverError` (v1, v2).** On the AERPAW testbed, once an armed vehicle that was in GUIDED reports another mode (safety pilot, failsafe, or the C-VM collision hold), aerpawlib stops commanding it until it disarms: a running `set_velocity` stream goes quiet without a stop setpoint, and `goto`, `takeoff`, `land`, `set_heading`, `set_velocity` and `set_groundspeed` raise `VehicleTakenOverError`. Before, the next command switched back to GUIDED, which the C-VM filter treats as fatal, so the script was cut off with no error. A LAND that aerpawlib commanded is not a takeover. Outside AERPAW nothing changes.

## [1.12.0] (2026-10-24)

### Summary

GUIDED commands sent through `mavlink_direct` reach the vehicle again, and copters on AERPAW take off high enough for velocity control to start right away.

### Fixed

- **Velocity, GUIDED, and yaw commands never reached the vehicle.** `resolve_mav_sysid` fell back to `System._sysid`, which is MAVSDK's own GCS id (245), and MAVSDK drops a message for a system it has no link to. Unless `AP_EXPENV_MAV_SYSID` or `MAV_SYSID` was set, `set_velocity` setpoints, the switch to GUIDED, and condition-yaw were dropped ("Sending message failed"). v1 and v2 now take the system id from the autopilot's SYS_STATUS. Rover velocity integration tests cover it against SITL.

### Added

- **`min_takeoff_alt`.** Optional copter safety config key (default `min_alt`), returned by `get_limitations`. Takeoffs below it are rejected. A takeoff floor above `min_alt` means `takeoff()`, which returns at 95% of the target, only returns once the copter is above `min_alt`, so the C-VM filter accepts velocity commands right away.

## [1.11.0] (2026-10-21)

### Summary

Fail closed on the AERPAW testbed. Drone and rover velocity control work there without leaving GUIDED, movement commands no longer stick after a timeout, and the safety checker, CLI, runner, and ZMQ paths reject inputs that used to fail open or hang the process.

### Fixed

- **`set_velocity` on AERPAW.** MAVSDK offboard is gone: its `offboard.stop()` switched to LOITER/HOLD, and the C-VM filter ends the experiment on that mode change. v1 and v2 `Drone` and `Rover` now stream `SET_POSITION_TARGET_LOCAL_NED` velocity setpoints through `mavlink_direct` in GUIDED. A drone faces its locked or current heading and stops by hovering (zero velocity); a rover stops with a speed-0 setpoint at its current heading, and a zero vector does the same instead of steering north. The vehicle never leaves GUIDED, in SITL or on the testbed.
- **Velocity kept running after a script ended.** Cancelling the velocity task (runner shutdown, v1 `close()`, v2 `close()`/`aclose()`) or a send error now sends the stop setpoint. Replacing or stopping a velocity command waits for the old stream to exit, so a stale setpoint can no longer follow the next command.
- **`set_velocity` input checks.** A non-finite velocity or a negative or non-finite duration raises `VelocityError` before anything is sent.
- **A failed goto, takeoff, or yaw blocked the next land.** The shared ready predicate stayed false after a timeout or action error, so `land()` waited out another full timeout and never sent LAND. The predicate is cleared on those failures.
- **Goto with an unknown home altitude.** A missing, non-finite, or (0, 0) home is refused. AMSL 0 is accepted once a home message has arrived, which is what AERPAW SITL reports (`--home lat,lon,0`).
- **Safety checker fail-open inputs.** Non-finite altitudes, speeds, and waypoints are rejected. Configured limits must be finite with min ≤ max or the server does not start. Takeoff outside an include fence or inside a no-go zone is rejected. `taking_off_or_landing` skips copter altitude limits only when the flag is exactly `True`.
- **Geofence KML.** v1 and v2 reject a file that is not exactly one polygon, has a hole, or has a non-finite coordinate. All current AHN fence files are one polygon and still load.
- **CLI runner discovery.** A subclass of a user runner is the mission that flies. Two unrelated runners in one script are rejected before anything is instantiated.
- **Failed connect.** A blank `--conn` is rejected. `tcp:` and `udp:` strings are rewritten to MAVSDK form. `mavsdk_server` processes started by the CLI are killed on connect failure and on SIGTERM, instead of staying up on the gRPC port.
- **External processes.** Commands are argv, not a shell, so a redirect path cannot run extra commands. Stdout is drained so a full pipe cannot wedge `wait()` after `kill()`.
- **ZMQ coordination.** Control frames are JSON. A reliable send completes only after the recipient's handler accepts it, and a peer that stops sending HELLO expires.
- **OEO checkpoint client.** A hung forwarder is retried once. A write that still fails raises the `requests` error, as before, so a lost checkpoint is never silent. A read that still fails returns the "not set" value (`False`, `0`, or `""`). Client sockets close with `linger=0`.

### Added

- **`get_limitations`.** The safety checker returns the configured vehicle type and speed and altitude limits. Responses without a data field are unchanged on the wire.
- **`max_vertical_speed`.** Optional copter safety config key (default 5 m/s), returned by `get_limitations`. The C-VM filter refuses velocity setpoints climbing or descending faster.
- **v2 `Rover.stop_velocity`.** `stop_velocity` moved to the v2 base `Vehicle`, so rovers have it too.

### Removed

- **`OFFBOARD_STOP_SETTLE_DELAY_S` (v1, v2) and `VELOCITY_LOOP_HANDOFF_DELAY_S` (v2).** Nothing waits on offboard any more.

## [1.10.1] (2026-09-23)

### Summary

Bug fixes for timed `set_velocity` race conditions and duration handling, latitude-scaled `Coordinate.bearing`, checkpoint URL encoding, and `ExternalProcess` stream redirection.

### Fixed

- **Timed `set_velocity` stopping the next command.** When a `set_velocity(..., duration=...)` expired, its loop zeroed velocity, waited a settle delay, then called `offboard.stop()` without checking for a newer command. A `set_velocity` issued during that delay (e.g. `set_velocity(v, duration=5)`, `sleep(5)`, `set_velocity(v2)`) was cut off. Stale loops now leave offboard alone when a newer command owns it (v1 and v2, drone and rover).
- **v2 `set_velocity(duration=0)` held forever.** `duration=0` was treated like `None`. It now stops right away.
- **`Coordinate.bearing` ignored latitude.** Raw degree deltas were used, so at 35.7°N a true 45° bearing read about 51°. This is the default yaw for `Drone.goto_coordinates`. The longitude delta is now scaled by `cos(latitude)` (v1 and v2).
- **Checkpoint names were not URL-encoded.** A name with `/`, `?`, `#` or `&` produced a malformed checkpoint URL (v1 and v2).
- **v2 `ExternalProcess` ignored `stdin` / `stdout` files.** With a file name the child inherited the parent's streams instead of reading or writing the file. The files are now opened and passed to the child.

## [1.10.0] (2026-09-03)

### Summary

AERPAW Virtual UAV follow-ups after 1.9.2: example land/RTL, CLI API detection, HOLD vs GUIDED on the testbed, and a MAVSDK 3.17 pin.

### Fixed

- **`plan_example` home at alt 0.** After a plan with no RTL item the example called `goto_coordinates(drone.home_coords)` (relative alt 0). That is rejected by the C-VM checker (`min_alt` 20). It now uses `return_to_launch()` (goto home at current altitude, then land).
- **Documented preplanned `--file`.** `preplanned_trajectory.py` / `plan_example.py` docstrings cited `plans/default.plan` (missing) or a KML. Both now point at `examples/v2/zmq_preplanned_orbit/orbit.plan`.
- **CLI `--api-version`.** Omitting the flag infers v1 or v2 from the script's Runner class. Passing the other API refuses to start with a clear error instead of `No Runner class found`.
- **HOLD is not GUIDED on AERPAW.** `_set_guided_mode` no longer treats MAVSDK `HOLD` (ArduCopter LOITER 5) as already-GUIDED when the copter filter is in play. From HOLD it still sends `COMMAND_LONG` 176 GUIDED.
- **`--no-aerpaw-environment` on a live E-VM.** v2 refuses the flag when experiment env vars are set and the OEO forwarder answers ping. `action.hold()` is also skipped whenever the forwarder is reachable, even if the platform client was not attached.
- **Closed-square examples.** `state_machine_example.py` and `squareoff_logging.py` call `return_to_launch()` before landing so a later extra leg cannot violate the 5 m land-at-takeoff rule.
- **Safety-checker takeoff pad.** `validate_takeoff_command` is altitude-only. It no longer records a land pin (the C-VM filter pins land to the first forwarded armed `NAV_TAKEOFF`).

### Changed

- Runtime dependency is `mavsdk>=3.17.2,<3.18` (encodings verified against the 2026 copter allow-list: takeoff `COMMAND_LONG` 22 alt in `param7`, goto `COMMAND_INT` 192, land `COMMAND_LONG` 21, GUIDED `COMMAND_LONG` 176).

## [1.9.2] (2026-08-31)

### Summary

Documentation corrections for local SITL and AERPAW takeoff/landing policy. GUIDED mode is set with `MAV_CMD_DO_SET_MODE`.

### Fixed

- **Docs.** Local SITL examples include `--no-aerpaw-environment`. Tutorial takeoff is 25 m (`min_alt` 20). Tests README matches current SITL logs and `SIM_SPEEDUP` default. Safety docs note landing within 5 m of takeoff.
- **GUIDED mode command.** Use `MAV_CMD_DO_SET_MODE` (COMMAND_LONG 176) instead of `SET_MODE`.

## [1.9.1] (2026-08-31)

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

## [1.9.0] (2026-08-25)

### Summary

Testbed compatibility fix for **v1 and v2**. The library-level safety checker now targets the C-VM in AERPAW, helper underscore flags still work, and auto RTL matches old aerpawlib (success only).

### Fixed

- **AERPAW safety-checker default host.** The library-level client no longer defaults to `127.0.0.1:14580` on the E-VM. In AERPAW it uses the C-VM address from `AP_EXPENV_OEOCVM_XM` (typically `192.168.32.25`), the same source as OEO.
- **Helper underscore safety flags.** Unmatched args such as `--safety_checker_ip` / `--safety_checker_port` still pass through to the script. The library-level client also reads those extra args, so helpers do not have to switch to dashed flags.

### Changed

- Auto RTL/RTH runs only after a successful mission (unless `--skip-rtl`). Ctrl-C, script errors, and heartbeat loss no longer command RTL; the last GUIDED setpoint remains. Examples use `--safety-checker-ip` / `--safety-checker-port` instead of extra-arg underscore forms.

## [1.8.0] (2026-08-16)

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

## [1.7.0] (2026-07-13)

Bugfix release on the way to general availability: CLI adds the script parent directory to `sys.path`; drones and rovers switch to GUIDED via MAVLink before arming; `set_groundspeed` uses `set_current_speed`; connection-string scheme checks are left to MAVSDK. See the [1.7.0 GitHub release](https://github.com/AERPAW/aerpawlib/releases/tag/1.7.0).

## [1.6.0] (2026-06-12)

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

## [1.5.1] and earlier

See git history for prior releases. Notable milestones: documentation overhaul, status bar improvements, v2 lifecycle hardening, and initial dual-API (v1/v2) split.
