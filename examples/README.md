# aerpawlib Examples

## Directory Structure

```
examples/
├── v1/                          # v1 API (MAVSDK-based)
│   ├── basic_example.py         # Square flight pattern
│   ├── basic_runner.py          # Minimal BasicRunner
│   ├── figure_eight.py          # Figure-8 pattern
│   ├── circle.py                # Circular flight
│   ├── squareoff_logging.py     # StateMachine + background logging
│   ├── preplanned_trajectory.py # Load QGroundControl .plan file
│   ├── hide_rover.py            # Rover plan + geofence hide
│   ├── external_runner.py       # ExternalProcess usage
│   ├── zmq_runner/              # Leader/follower ZMQ coordination
│   │   ├── leader.py
│   │   ├── follower.py
│   │   └── README.md
│   └── zmq_preplanned_orbit/    # Multi-drone orbit mission
│       ├── consts.py
│       ├── drone_orbiter.py
│       ├── drone_tracer.py
│       ├── ground_coordinator.py
│       ├── orbit.plan
│       └── README.md
└── v2/                          # v2 API (modern, async-first)
    ├── at_init_example.py       # StateMachine with pre-arm setup hooks
    ├── basic_example.py         # Square flight pattern
    ├── basic_runner.py          # Minimal BasicRunner
    ├── circle.py                # Circular flight using velocity control
    ├── command_handle_cancel_example.py # Cancel non-blocking goto mid-flight
    ├── command_handle_example.py # Non-blocking command handle progress querying
    ├── command_validation_example.py # Pre-check capability validation
    ├── dummy_vehicle_example.py # Dry-run / CI vehicle mock
    ├── enhanced_example.py      # Preflight checks and pre-command validations
    ├── external_runner.py       # ExternalProcess usage
    ├── figure_eight.py          # Figure-8 waypoint pattern
    ├── geofence.kml             # KML file defining geofence boundaries
    ├── geofence_example.py      # Waypoint/path validation against KML
    ├── hide_rover.py            # Rover plan + geofence hide
    ├── logging_example.py       # Structured logging with LogComponent
    ├── plan_example.py          # Parsing and executing QGroundControl plan
    ├── preplanned_trajectory.py # Load QGroundControl .plan file
    ├── rover_example.py         # Ground vehicle waypoint navigation
    ├── squareoff_logging.py     # StateMachine + background logging
    ├── state_machine_example.py # Timed state machine with background logging
    ├── velocity_example.py      # Guided mode velocity control pattern
    ├── zmq_runner/              # Leader/follower ZMQ coordination
    │   ├── leader.py
    │   ├── follower.py
    │   └── README.md
    └── zmq_state_machine_example.py # ZmqStateMachine with expose_zmq
```

## Quick Reference

| Example | Version | Description |
|---------|---------|-------------|
| `basic_example` | v1, v2 | Square flight pattern (10m × 10m) |
| `basic_runner` | v1, v2 | Minimal `BasicRunner` – takeoff, fly north, land |
| `figure_eight` | v1, v2 | Figure-8 waypoint pattern |
| `circle` | v1, v2 | Circular flight using velocity control |
| `squareoff_logging` | v1, v2 | Square flight with background position logging |
| `preplanned_trajectory` | v1, v2 | Waypoints loaded from QGroundControl `.plan` file |
| `hide_rover` | v1, v2 | Rover follows plan, then hides in geofence |
| `external_runner` | v1, v2 | Spawns and interacts with external processes |
| `zmq_runner` | v1, v2 | Leader/follower multi-vehicle coordination via ZMQ |
| `zmq_preplanned_orbit` | v1 | Multi-drone tracer + orbiter mission |
| `enhanced_example` | v2 | Preflight checks and pre-command validations |
| `rover_example` | v2 | Ground vehicle waypoint navigation |
| `velocity_example` | v2 | Guided mode velocity control pattern |
| `command_handle_example` | v2 | Non-blocking command handle progress querying |
| `command_handle_cancel_example` | v2 | Cancel non-blocking goto mid-flight (triggers RTL) |
| `command_validation_example` | v2 | Pre-check capability validation |
| `geofence_example` | v2 | Waypoint and path validation using geofence KML |
| `logging_example` | v2 | Structured logging using `get_logger` and `LogComponent` |
| `dummy_vehicle_example` | v2 | Dry-run / CI vehicle mock using `DummyVehicle` |
| `at_init_example` | v2 | StateMachine with pre-arm setup hooks |
| `plan_example` | v2 | Parsing and executing QGroundControl waypoint files |
| `state_machine_example` | v2 | Timed state machine with background logging |
| `zmq_state_machine_example` | v2 | Remote transition execution using `ZmqStateMachine` |

## Running Examples

### v1 API

```bash
# Basic examples
aerpawlib --api-version v1 --script examples/v1/basic_example.py \
    --vehicle drone --conn udp://127.0.0.1:14550

aerpawlib --api-version v1 --script examples/v1/basic_runner.py \
    --vehicle drone --conn udp://127.0.0.1:14550

aerpawlib --api-version v1 --script examples/v1/figure_eight.py \
    --vehicle drone --conn udp://127.0.0.1:14550

# State machine examples
aerpawlib --script examples/v1/circle.py \
    --vehicle drone --conn udp://127.0.0.1:14550

aerpawlib --script examples/v1/squareoff_logging.py \
    --vehicle drone --conn udp://127.0.0.1:14550

# Preplanned trajectory (requires .plan file)
aerpawlib --script examples/v1/preplanned_trajectory.py \
    --vehicle drone --conn udp://127.0.0.1:14550 --file mission.plan

# External process
aerpawlib --script examples/v1/external_runner.py \
    --vehicle drone --conn udp://127.0.0.1:14550
```

### v2 API

```bash
# Basic examples
aerpawlib --api-version v2 --script examples/v2/basic_example.py \
    --vehicle drone --conn udpin://127.0.0.1:14550

aerpawlib --api-version v2 --script examples/v2/basic_runner.py \
    --vehicle drone --conn udpin://127.0.0.1:14550

# State machine examples
aerpawlib --api-version v2 --script examples/v2/state_machine_example.py \
    --vehicle drone --conn udpin://127.0.0.1:14550

# Dry run with DummyVehicle (no connection or hardware needed)
aerpawlib --api-version v2 --script examples/v2/dummy_vehicle_example.py \
    --vehicle none --conn ""
```

### ZMQ Multi-Vehicle (v1)

Requires `aerpawlib-run-proxy` in a separate terminal first.

```bash
# Leader/follower
aerpawlib --script examples/v1/zmq_runner/leader.py \
    --conn udp://127.0.0.1:14550 --vehicle drone \
    --zmq-identifier leader --zmq-proxy-server 127.0.0.1

aerpawlib --script examples/v1/zmq_runner/follower.py \
    --conn udp://127.0.0.1:14551 --vehicle drone \
    --zmq-identifier follower --zmq-proxy-server 127.0.0.1
```

See [v1/zmq_runner/README.md](v1/zmq_runner/README.md) and [v1/zmq_preplanned_orbit/README.md](v1/zmq_preplanned_orbit/README.md) for ZMQ setup details.

### ZMQ Multi-Vehicle (v2)

```bash
aerpawlib-run-proxy  # Terminal 1

aerpawlib --api-version v2 --script examples/v2/zmq_state_machine_example.py \
    --vehicle drone --conn udpin://127.0.0.1:14550 \
    --zmq-identifier leader --zmq-proxy-server 127.0.0.1  # Terminal 2
```


## Notable Examples

`squareoff_logging:` Demonstrates `StateMachine` with `@background` for parallel position logging. Uses dynamic state transitions (`_legs`, `_current_leg`) to fly a square.

`preplanned_trajectory:` Loads waypoints from a QGroundControl `.plan` file. Uses `at_init`, `timed_state`, and `ExternalProcess` (ping) for waypoint-based missions.

