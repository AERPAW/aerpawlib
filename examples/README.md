# aerpawlib Examples

## Directory Structure

```
examples/
├── v1/                          # v1 API (MAVSDK-based)
│   ├── basic_example.py         # Square flight pattern
│   ├── basic_runner.py          # Minimal BasicRunner
│   ├── figure_eight.py          # Figure-8 pattern
│   ├── circle.py               # Circular flight
│   ├── squareoff_logging.py     # StateMachine + background logging
│   ├── preplanned_trajectory.py # Load QGroundControl .plan file
│   ├── hide_rover.py            # Rover plan + geofence hide
│   ├── external_runner.py       # ExternalProcess usage
│   ├── zmq_runner/              # Leader/follower ZMQ coordination
│   │   ├── leader.py
│   │   ├── follower.py
│   │   └── README.md
│   └── zmq_preplanned_orbit/   # Multi-drone orbit mission
│       ├── drone_orbiter.py
│       ├── drone_tracer.py
│       ├── ground_coordinator.py
│       ├── orbit.plan
│       └── README.md
└── v2/                          # v2 API (modern, async-first)
    ├── basic_example.py
    ├── command_handle_example.py
    ├── enhanced_example.py
    ├── state_machine_example.py
    └── test_runner.py
```

## Quick Reference

| Example | Description |
|---------|-------------|
| `basic_example` | Square flight pattern (10m × 10m) |
| `basic_runner` | Minimal BasicRunner – takeoff, fly north, land |
| `figure_eight` | Figure-8 waypoint pattern |
| `circle` | Circular flight using velocity control |
| `squareoff_logging` | Square flight with background position logging |
| `preplanned_trajectory` | Waypoints from QGroundControl `.plan` file |
| `hide_rover` | Rover follows plan, then hides in geofence |
| `external_runner` | Spawn and interact with external processes |
| `zmq_runner` | Leader/follower multi-vehicle coordination |
| `zmq_preplanned_orbit` | Two drones: tracer + orbiter |

## Running Examples

### v1 API

```bash
# Basic examples
aerpawlib --api-version v1 --script examples.v1.basic_example \
    --vehicle drone --conn udp://127.0.0.1:14550

aerpawlib --api-version v1 --script examples.v1.basic_runner \
    --vehicle drone --conn udp://127.0.0.1:14550

aerpawlib --api-version v1 --script examples.v1.figure_eight \
    --vehicle drone --conn udp://127.0.0.1:14550

# State machine examples
aerpawlib --script examples.v1.circle \
    --vehicle drone --conn udp://127.0.0.1:14550

aerpawlib --script examples.v1.squareoff_logging \
    --vehicle drone --conn udp://127.0.0.1:14550

# Preplanned trajectory (requires .plan file)
aerpawlib --script examples.v1.preplanned_trajectory \
    --vehicle drone --conn udp://127.0.0.1:14550 --file mission.plan

# External process
aerpawlib --script examples.v1.external_runner \
    --vehicle drone --conn udp://127.0.0.1:14550
```

### ZMQ Multi-Vehicle (v1)

Requires `aerpawlib --run-proxy` in a separate terminal first.

```bash
# Leader/follower
aerpawlib --script examples.v1.zmq_runner.leader \
    --conn udp://127.0.0.1:14550 --vehicle drone \
    --zmq-identifier leader --zmq-proxy-server 127.0.0.1

aerpawlib --script examples.v1.zmq_runner.follower \
    --conn udp://127.0.0.1:14551 --vehicle drone \
    --zmq-identifier follower --zmq-proxy-server 127.0.0.1
```

See [v1/zmq_runner/README.md](v1/zmq_runner/README.md) and [v1/zmq_preplanned_orbit/README.md](v1/zmq_preplanned_orbit/README.md) for ZMQ setup details.


## Notable Examples

`squareoff_logging:` Demonstrates `StateMachine` with `@background` for parallel position logging. Uses dynamic state transitions (`_legs`, `_current_leg`) to fly a square.

`preplanned_trajectory:` Loads waypoints from a QGroundControl `.plan` file. Uses `at_init`, `timed_state`, and `ExternalProcess` (ping) for waypoint-based missions.
