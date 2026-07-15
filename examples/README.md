# aerpawlib Examples

## Quick Reference

| Example                         | Version | Description                                              |
|---------------------------------|---------|----------------------------------------------------------|
| `basic_example`                 | v1, v2  | Square flight pattern (10m × 10m)                        |
| `basic_runner`                  | v1, v2  | Minimal `BasicRunner`: takeoff, fly north, land         |
| `figure_eight`                  | v1, v2  | Figure-8 waypoint pattern                                |
| `circle`                        | v1, v2  | Circular flight using velocity control                   |
| `squareoff_logging`             | v1, v2  | Square flight with background position logging           |
| `preplanned_trajectory`         | v1, v2  | Waypoints loaded from QGroundControl `.plan` file        |
| `hide_rover`                    | v1, v2  | Rover follows plan, then hides in geofence               |
| `external_runner`               | v1, v2  | Spawns and interacts with external processes             |
| `zmq_runner`                    | v1, v2  | Leader/follower multi-vehicle coordination via ZMQ       |
| `zmq_preplanned_orbit`          | v1, v2  | Multi-drone tracer + orbiter mission                     |
| `gps_logger`                    | v1      | Periodically log vehicle position and state to CSV       |
| `guided_mission_ping_iperf`     | v1      | Preplanned trajectory with ping/iperf network traffic    |
| `rover_search`                  | v1      | Drone search algorithm using safety checker and RSSI     |
| `enhanced_example`              | v2      | Preflight checks and pre-command validations             |
| `rover_example`                 | v2      | Ground vehicle waypoint navigation                       |
| `velocity_example`              | v2      | Guided mode velocity control pattern                     |
| `command_handle_example`        | v2      | Non-blocking command handle progress querying            |
| `command_handle_cancel_example` | v2      | Cancel non-blocking goto mid-flight (triggers RTL)       |
| `command_validation_example`    | v2      | Pre-check capability validation                          |
| `geofence_example`              | v2      | Waypoint and path validation using geofence KML          |
| `logging_example`               | v2      | Structured logging using `get_logger` and `LogComponent` |
| `dummy_vehicle_example`         | v2      | Dry-run / CI vehicle mock using `DummyVehicle`           |
| `at_init_example`               | v2      | StateMachine with pre-arm setup hooks                    |
| `plan_example`                  | v2      | Parsing and executing QGroundControl waypoint files      |
| `state_machine_example`         | v2      | Timed state machine with background logging              |
| `zmq_state_machine_example`     | v2      | Remote transition execution using `ZmqStateMachine`      |

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

# GPS Logger (periodically log telemetry to CSV)
aerpawlib --script examples/v1/gps_logger.py \
    --vehicle drone --conn udp://127.0.0.1:14550 --output logs.csv --samplerate 2

# Guided mission with background traffic testing (ping/iperf)
aerpawlib --script examples/v1/guided_mission_ping_iperf.py \
    --vehicle drone --conn udp://127.0.0.1:14550 --file plans/default.plan --destination_ip 127.0.0.1

# Rover search (search for rover utilizing safety checker and RSSI values)
aerpawlib --script examples/v1/rover_search.py \
    --vehicle drone --conn udp://127.0.0.1:14550 --fake_radio True --search_time 10
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

