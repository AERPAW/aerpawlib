# aerpawlib Starter Profiles

## Squareoff with Logging

`squareoff_logging.py` is an example aerpawlib script that will fly a drone in
a 10m by 10m square, while using the `StateMachine`'s `background` utility to
continually log the drone's position to a file. This example is intended to
demonstrate how to write a dynamic state machine as well as use the
`background` tool.

This script can be run on either a drone or a rover. To run it, use aerpawlib:

```
python -m aerpawlib --conn ... --script squareoff_logging --vehicle drone
```

When run, it will continually output positional data to a log file that can be
specified using the `--output` param. The sample rate can be changed using
`--samplerate`. If no file is specified, it will default to outputting to a
file named `GPS_DATA_YYYY-MM-DD_HH:MM:SS.csv`. This output format is below:

```
line num,lon,lat,alt,battery voltage,timestamp,GPS fix type,# visible sats

timestamp format: YYYY-MM-DD HH:MM:SS.ssssss
```

A flowchart of the various states is below:

```
┌───────┐drone ┌──────────┐
│ start ├──────► take_off │
└───┬───┘      └─────┬────┘
    │                │
    ├────────────────┘
    │
┌───▼───────┐
│ leg_north ├───────────┐
│           │           │
│ leg_west  │           │
│           │       ┌───▼─────────┐
│ leg_south ◄───────┤ at_position │
│           │pick   └───┬──┬────▲─┘
│ leg_east  │based on   │  └────┘sleep 5s
└───────────┘current_leg│
                    ┌───▼────┐drone ┌──────┐
                    │ finish ├──────► land │
                    └────────┘      └──────┘
```

The centerpiece of this script, aside from the background logging, is the
dynamic state changing. By default, the only state stored by a `StateMachine`
is the current state *function* -- individually, each function can be
considered to be stateless (with side effects affecting the vehicle).

To introduce additional state into the state machine, all you have to do is add
method variables to your `StateMachine` derived object. This script uses
`_legs: List[str]` and `_current_leg: int` to do that. `_current_leg` is
altered and interpreted by the `at_position` state to then dynamically pick the
next state on the fly.

## Preplanned Trajectory

`preplanned_trajectory.py` is an example aerpawlib script that makes a vehicle
fly between different waypoints read from a `.plan` file generated using
`QGroundControl`. This example is a good starting point for experiments that
make use of non-dynamic flight plans.

This script can be run on either a drone or rover. To run it, use aerpawlib:

```
python -m aerpawlib --conn ... --script preplanned_trajectory --vehicle drone \
    --file <.plan file to use>
```

When run, it will load in the `.plan` file located at the path specified by
`--plan` and then send the drone to each waypoint specified sequentially in it.

A flowchart of the various states is below:

```
┌──────────┐
│ take_off │
└──────┬───┘
       │
       ├────────────────────────────────────────┐
       │                                        │
┌──────▼────────┐    ┌────────────┐     ┌───────┴─────┐
│ next_waypoint ├────► in_transit ├─────► at_waypoint │
└──────┬────────┘    └────────────┘     └─────────────┘
       │
    ┌──▼──┐
    │ rtl │
    └─────┘
```

This script includes several states that can be used as hooks to introduce
custom logic that runs during various parts of the flight plan.

`in_transit` is a function that will be called once after the script picks a
waypoint for the vehicle to go to, at which point it blocks until the vehicle
arrives. Custom logic can be added before the `await` statement, at which point
the script blocks while waiting for the drone to finish moving.

To add custom logic that waits for the drone to finish moving, you can
continually poll `drone.done_moving()`.

`at_waypoint` is a timed state that is called once the vehicle arrives at a
waypoint. As a timed state, it is guaranteed to be called repeatedly for at
least `duration` seconds.

---

# aerpawlib Examples

This directory contains example scripts demonstrating how to use aerpawlib for drone control.

## Directory Structure

```
examples/
├── v1/                      # v1 API examples (MAVSDK-based, DroneKit-compatible interface)
│   ├── basic_example.py         # Simple square flight pattern
│   ├── circle_flight.py         # Circular flight using velocity control
│   ├── figure_eight.py          # Figure-8 pattern with waypoints
│   ├── state_machine_logging.py # StateMachine with background logging
│   ├── survey_grid.py           # Lawnmower survey pattern
│   └── waypoint_mission.py      # Load and fly .plan file missions
├── v2/                      # v2 API examples (Modern Pythonic interface)
│   ├── basic_example.py         # Simple mission with telemetry
│   ├── command_handle_example.py # Non-blocking command execution
│   ├── enhanced_example.py      # Advanced features
│   ├── logging_example.py       # Custom logging configuration
│   └── state_machine_example.py # StateMachine pattern
└── legacy/                  # Legacy DroneKit-based examples (should still be compatible with v1 runner)
    ├── basic_runner.py
    ├── circle.py
    ├── squareoff_logging.py
    └── ...
```

## Running Examples

### v1 API Examples

```bash
# Basic square flight
python -m aerpawlib --api v1 --script examples.v1.basic_example \
    --vehicle drone --conn udp:127.0.0.1:14550

# Circle flight with custom parameters
python -m aerpawlib --api v1 --script examples.v1.circle_flight \
    --vehicle drone --conn udp:127.0.0.1:14550 \
    --radius 20 --velocity 3 --laps 3

# Survey grid pattern
python -m aerpawlib --api v1 --script examples.v1.survey_grid \
    --vehicle drone --conn udp:127.0.0.1:14550 \
    --width 50 --height 50 --spacing 10

# State machine with logging
python -m aerpawlib --api v1 --script examples.v1.state_machine_logging \
    --vehicle drone --conn udp:127.0.0.1:14550 \
    --output flight_log.csv --samplerate 10

# Waypoint mission from .plan file
python -m aerpawlib --api v1 --script examples.v1.waypoint_mission \
    --vehicle drone --conn udp:127.0.0.1:14550 \
    --plan mission.plan
```

### v2 API Examples

```bash
# Basic example
python -m aerpawlib --api v2 --script examples.v2.basic_example \
    --vehicle drone --conn udp:127.0.0.1:14550

# State machine example
python -m aerpawlib --api v2 --script examples.v2.state_machine_example \
    --vehicle drone --conn udp:127.0.0.1:14550

# Non-blocking command handles
python -m aerpawlib --api v2 --script examples.v2.command_handle_example \
    --vehicle drone --conn udp:127.0.0.1:14550
```


# Legacy Documentation

The following documentation is for legacy examples (deprecated, use v1 or v2 instead):

## Squareoff with Logging

`squareoff_logging.py` is an example aerpawlib script that will fly a drone in
a 10m by 10m square, while using the `StateMachine`'s `background` utility to
continually log the drone's position to a file. This example is intended to
demonstrate how to write a dynamic state machine as well as use the
`background` tool.

This script can be run on either a drone or a rover. To run it, use aerpawlib:

```
python -m aerpawlib --conn ... --script squareoff_logging --vehicle drone
```

When run, it will continually output positional data to a log file that can be
specified using the `--output` param. The sample rate can be changed using
`--samplerate`. If no file is specified, it will default to outputting to a
file named `GPS_DATA_YYYY-MM-DD_HH:MM:SS.csv`. This output format is below:

```
line num,lon,lat,alt,battery voltage,timestamp,GPS fix type,# visible sats

timestamp format: YYYY-MM-DD HH:MM:SS.ssssss
```

A flowchart of the various states is below:

```
┌───────┐drone ┌──────────┐
│ start ├──────► take_off │
└───┬───┘      └─────┬────┘
    │                │
    ├────────────────┘
    │
┌───▼───────┐
│ leg_north ├───────────┐
│           │           │
│ leg_west  │           │
│           │       ┌───▼─────────┐
│ leg_south ◄───────┤ at_position │
│           │pick   └───┬──┬────▲─┘
│ leg_east  │based on   │  └────┘sleep 5s
└───────────┘current_leg│
                    ┌───▼────┐drone ┌──────┐
                    │ finish ├──────► land │
                    └────────┘      └──────┘
```

The centerpiece of this script, aside from the background logging, is the
dynamic state changing. By default, the only state stored by a `StateMachine`
is the current state *function* -- individually, each function can be
considered to be stateless (with side effects affecting the vehicle).

To introduce additional state into the state machine, all you have to do is add
method variables to your `StateMachine` derived object. This script uses
`_legs: List[str]` and `_current_leg: int` to do that. `_current_leg` is
altered and interpreted by the `at_position` state to then dynamically pick the
next state on the fly.

## Preplanned Trajectory

`preplanned_trajectory.py` is an example aerpawlib script that makes a vehicle
fly between different waypoints read from a `.plan` file generated using
`QGroundControl`. This example is a good starting point for experiments that
make use of non-dynamic flight plans.

This script can be run on either a drone or rover. To run it, use aerpawlib:

```
python -m aerpawlib --conn ... --script preplanned_trajectory --vehicle drone \
    --file <.plan file to use>
```

When run, it will load in the `.plan` file located at the path specified by
`--plan` and then send the drone to each waypoint specified sequentially in it.

A flowchart of the various states is below:

```
┌──────────┐
│ take_off │
└──────┬───┘
       │
       ├────────────────────────────────────────┐
       │                                        │
┌──────▼────────┐    ┌────────────┐     ┌───────┴─────┐
│ next_waypoint ├────► in_transit ├─────► at_waypoint │
└──────┬────────┘    └────────────┘     └─────────────┘
       │
    ┌──▼──┐
    │ rtl │
    └─────┘
```

This script includes several states that can be used as hooks to introduce
custom logic that runs during various parts of the flight plan.

`in_transit` is a function that will be called once after the script picks a
waypoint for the vehicle to go to, at which point it blocks until the vehicle
arrives. Custom logic can be added before the `await` statement, at which point
the script blocks while waiting for the drone to finish moving.

To add custom logic that waits for the drone to finish moving, you can
continually poll `drone.done_moving()`.

`at_waypoint` is a timed state that is called once the vehicle arrives at a
waypoint. As a timed state, it is guaranteed to be called repeatedly for at
least `duration` seconds.
