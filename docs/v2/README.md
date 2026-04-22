# aerpawlib v2 API

v2 is a modern, async-first replacement for the v1 API. It eliminates the dual-loop architecture, ThreadSafeValue overhead, and function-attribute runners in favor of a single event loop, native async telemetry, descriptor-based decorators, and built-in safety/connection handling.

## Quick Start

```python
from aerpawlib.v2 import BasicRunner, Drone, VectorNED, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=10)
        await drone.goto_coordinates(drone.position + VectorNED(20, 0))
        await drone.land()
```

Run with:
```bash
aerpawlib --api-version v2 --script my_mission.py --vehicle drone --conn udpin://127.0.0.1:14550
```

### Structured JSONL (`--structured-log FILE`)

Machine-readable events are written one JSON object per line: `mission_start` / `mission_end`, throttled `telemetry` (position, velocity, attitude, battery, GPS, mode, armed), `command` events (e.g. `set_velocity`, `stop_velocity`, takeoff, goto), and `arm` / `disarm`. Omit the flag to disable file output.

## Architecture

- No background threads for MAVSDK. All commands use direct `await`.
- Subscriptions update plain attributes; no ThreadSafeValue.
- Runners use config dataclass (`BasicRunnerConfig`, `StateMachineConfig`) or decorators.
- Non-blocking commands with `progress`, `cancel()`, and `wait_done()`.

## Key Types

| Type                             | Purpose                                             |
|----------------------------------|-----------------------------------------------------|
| `Coordinate`                     | WGS84 position (lat, lon, alt)                      |
| `VectorNED`                      | NED displacement (north, east, down) in meters      |
| `Battery`, `GPSInfo`, `Attitude` | Telemetry dataclasses                               |
| `VehicleTask`                    | Non-blocking command with progress and cancellation |

## Vehicle API


### Connection
```python
vehicle = await Drone.connect("udpin://127.0.0.1:14550")
# With safety checker:
from aerpawlib.v2.safety import SafetyCheckerClient
vehicle = await Drone.connect("udpin://127.0.0.1:14550", safety=SafetyCheckerClient("127.0.0.1", 14580))
# With custom timeout:
vehicle = await Drone.connect("udpin://127.0.0.1:14550", timeout=60.0)
```

### Vehicle Properties

| Property      | Type                   | Description                                 |
|---------------|------------------------|---------------------------------------------|
| `position`    | `Coordinate`           | Current position (lat, lon, alt AGL)        |
| `home_coords` | `Optional[Coordinate]` | Home/launch position                        |
| `home_amsl`   | `float`                | Home altitude in AMSL meters                |
| `battery`     | `Battery`              | Battery status (voltage, current, level %)  |
| `gps`         | `GPSInfo`              | GPS status (fix_type, satellites_visible)   |
| `armed`       | `bool`                 | True if vehicle is armed                    |
| `heading`     | `float`                | Current heading in degrees                  |
| `velocity`    | `VectorNED`            | Current velocity in m/s                     |
| `attitude`    | `Attitude`             | Roll, pitch, yaw in radians                 |
| `mode`        | `str`                  | Current flight mode name                    |
| `armable`     | `bool`                 | True if vehicle can be armed                |
| `connected`   | `bool`                 | True if connection is active and not closed |
| `closed`      | `bool`                 | True if `close()` has been called           |

### Drone Commands (blocking)
```python
await drone.takeoff(altitude=10)
await drone.goto_coordinates(target, tolerance=2)
await drone.set_heading(90)
await drone.land()
await drone.return_to_launch()
await drone.set_velocity(VectorNED(5, 0, 0), duration=10)
await drone.stop_velocity()       # stop active velocity command
await drone.set_groundspeed(8.0)  # max cruise speed in m/s
```

### Non-blocking goto
```python
handle = await drone.goto_coordinates(target, blocking=False)
print(handle.progress)   # 0.0 to 1.0
handle.cancel()          # triggers RTL on drone, hold on rover
await handle.wait_done() # raises if error occurred
```

### VehicleTask API

| Method / Property | Description                                                 |
|-------------------|-------------------------------------------------------------|
| `progress`        | Float 0.0–1.0 progress estimate                             |
| `is_done()`       | True when command has completed, errored, or been cancelled |
| `is_cancelled()`  | True after `cancel()` has been called                       |
| `cancel()`        | Request cancellation (triggers on_cancel callback)          |
| `wait_done()`     | Await completion; re-raises any error                       |

### Arm / Disarm
```python
await vehicle.set_armed(True)   # arm
await vehicle.set_armed(False)  # disarm
```

### Close
```python
vehicle.close()  # cancel all telemetry and command tasks, release connection
```

## Rover API

`Rover` is a ground-vehicle variant that shares the base `Vehicle` interface. Key differences:

- Uses **ground distance** (2D) for arrival tolerance; default tolerance is `2.1` m.
- `set_velocity` ignores the `down` component (rovers don't fly).
- There is no `takeoff`, `land`, `return_to_launch`, `set_heading`, or `stop_velocity` method.
- Switches to ArduPilot GUIDED mode automatically before arming.

```python
from aerpawlib.v2 import BasicRunner, Rover, entrypoint

class GroundMission(BasicRunner):
    @entrypoint
    async def run(self, rover: Rover):
        await rover.goto_coordinates(target, tolerance=3.0)
        await rover.set_velocity(VectorNED(2, 0, 0), duration=5)
```

### Rover Commands

#### `await goto_coordinates(coordinates, tolerance=2.1, timeout=300, blocking=True)`

Navigate to a position (2D ground). `target_heading` is accepted but ignored.

```python
await rover.goto_coordinates(Coordinate(35.7275, -78.696, 0))
handle = await rover.goto_coordinates(target, blocking=False)
```

#### `await set_velocity(velocity_vector, global_relative=True, duration=None)`

Set velocity in NED frame. Down component is zeroed.

```python
await rover.set_velocity(VectorNED(2, 0, 0), duration=10)  # 2 m/s north for 10s
```

## Runners

### BasicRunner
Single entry point:
```python
class MyScript(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        ...
```

### StateMachine
States with transitions:
```python
class MyMission(StateMachine):
    @state(name="start", first=True)
    async def start(self, drone: Drone):
        return "fly"

    @state(name="fly")
    async def fly(self, drone: Drone):
        return "land"

    @timed_state(name="hold", duration=5)
    async def hold(self, drone: Drone):
        return "land"

    @background
    async def monitor(self, drone: Drone):
        while True:
            print(drone.position)
            await asyncio.sleep(1)

    @at_init
    async def setup(self, drone: Drone):
        # Runs once before arm/first state
        print("Initialising mission")
```

### Decorators

| Decorator                                               | Class             | Description                                                      |
|---------------------------------------------------------|-------------------|------------------------------------------------------------------|
| `@entrypoint`                                           | `BasicRunner`     | Marks the single async entry point                               |
| `@state(name, first=False)`                             | `StateMachine`    | Defines a state; returns next state name or `None`               |
| `@timed_state(name, duration, loop=False, first=False)` | `StateMachine`    | State that runs for a fixed duration                             |
| `@background`                                           | `StateMachine`    | Runs concurrently with the state machine; restarted on exception |
| `@at_init`                                              | `StateMachine`    | Runs once before arm and before the first state                  |
| `@expose_zmq(name)`                                     | `ZmqStateMachine` | Exposes a state for remote ZMQ transition                        |
| `@expose_field_zmq(name)`                               | `ZmqStateMachine` | Exposes a method as a queryable ZMQ field                        |

#### `@at_init`

`@at_init` methods run sequentially before arm, before the first state starts. Use for one-time setup that should complete before flight:

```python
from aerpawlib.v2 import StateMachine, state, at_init

class MyMission(StateMachine):
    @at_init
    async def setup(self, drone):
        print(f"Home: {drone.home_coords}")

    @state(name="start", first=True)
    async def start(self, drone):
        await drone.takeoff(10)
        return None
```

### ZmqStateMachine

State machine with remote ZMQ control:

```python
from aerpawlib.v2 import ZmqStateMachine, Drone, state, expose_zmq, expose_field_zmq

class RemoteMission(ZmqStateMachine):
    @expose_zmq("fly")
    @state(name="fly", first=True)
    async def fly(self, drone: Drone):
        await drone.takeoff(10)
        return "land"

    @state(name="land")
    async def land(self, drone: Drone):
        await drone.land()
        return None

    @expose_field_zmq("altitude")
    async def get_altitude(self, drone: Drone):
        return drone.position.alt
```

Run with `--zmq-identifier` and `--zmq-proxy-server`. Start the ZMQ proxy first: `aerpawlib --run-proxy`.

#### `@expose_field_zmq(name)`

Mark an async method so other runners can query its return value over ZMQ using `query_field`:

```python
# In RemoteMission (above), exposes "altitude"
@expose_field_zmq("altitude")
async def get_altitude(self, drone):
    return drone.position.alt
```

#### `transition_runner(identifier, state_name)` / `query_field(identifier, field)`

Send cross-runner commands from within a `ZmqStateMachine`:

```python
# Trigger a state transition on another runner
await self.transition_runner("other-vehicle", "land")

# Query an exposed field from another runner
alt = await self.query_field("other-vehicle", "altitude")
```

### Config Dataclass

Runners can use explicit config instead of decorators:

```python
from aerpawlib.v2 import BasicRunner, BasicRunnerConfig

class MyMission(BasicRunner):
    config = BasicRunnerConfig(entrypoint="run")
    async def run(self, drone):
        ...
```

`StateMachineConfig` and `ZmqStateMachineConfig` are also available for explicit state machine configuration.

## QGroundControl Plan Files

```python
from aerpawlib.v2.plan import read_from_plan, get_location_from_waypoint

waypoints = read_from_plan("mission.plan")
for wp in waypoints:
    coord = get_location_from_waypoint(wp)
    await drone.goto_coordinates(coord)
```

`read_from_plan_complete` returns all waypoints including takeoff and RTL items; `read_from_plan` returns only navigation waypoints.

## Command Validation

Check if a command will succeed before running it:

```python
ok, msg = await drone.can_takeoff(10)
if not ok:
    print(f"Cannot takeoff: {msg}")
    return
await drone.takeoff(altitude=10)

ok, msg = await drone.can_goto(target)
if ok:
    await drone.goto_coordinates(target)

ok, msg = await drone.can_land()
```

`can_takeoff` checks armable status, GPS 3D fix, and minimum battery. `can_goto` validates tolerance bounds. Both also forward to the `SafetyCheckerClient` if one is configured.

## Safety Integration

Pass a safety client (`SafetyCheckerClient` or `NoOpSafetyChecker`) to `connect(safety=...)`. The vehicle constructor stores it for `can_takeoff`, `can_goto`, `can_land`. When running via CLI, aerpawlib builds the safety client and passes it automatically (see [Safety — Automatic Setup](safety.md#automatic-setup-via-cli-safety-checker-port)).

```python
from aerpawlib.v2.safety import SafetyCheckerClient

client = SafetyCheckerClient("127.0.0.1", 14580)
drone = await Drone.connect("udpin://127.0.0.1:14550", safety=client)
ok, msg = await drone.can_takeoff(10)
```

Or use the CLI: `--safety-checker-port 14580` (in AERPAW, defaults to 14580; outside AERPAW, optional with passthrough on failure).

## Geofence Utilities

Low-level polygon utilities used internally and available for custom geofence logic:

```python
from aerpawlib.v2 import read_geofence, inside, do_intersect

# Parse a KML file into a list of {'lat': ..., 'lon': ...} dicts
polygon = read_geofence("flight_area.kml")

# Check if a point is inside the polygon
if inside(lon=-78.696, lat=35.727, geofence=polygon):
    print("Inside geofence")

# Check if two line segments intersect
if do_intersect(p1x, p1y, p2x, p2y, q1x, q1y, q2x, q2y):
    print("Path crosses boundary")
```

## ExternalProcess

Async wrapper for launching and communicating with subprocesses:

```python
from aerpawlib.v2 import ExternalProcess

proc = ExternalProcess("python3", params=["-u", "sensor_reader.py"])
await proc.start()

# Read stdout line by line
line = await proc.read_line()

# Write to stdin
await proc.send_input("start\n")

# Wait until a line matching a regex appears in stdout
lines = await proc.wait_until_output(r"READY")

# Wait for the process to exit
await proc.wait_until_terminated()
```

## Testing Utilities

### MockVehicle

Minimal in-memory vehicle for pure unit tests that don't need MAVSDK:

```python
from aerpawlib.v2 import MockVehicle, Coordinate

vehicle = MockVehicle(
    position=Coordinate(35.727, -78.696, 0),
    armed=False,
    connected=True,
)
# Use as a vehicle argument in runner tests
```

### DummyVehicle

No-op vehicle that implements the full `Vehicle` interface but performs no actual MAVSDK calls. Useful for dry-run testing of full runner pipelines:

```python
from aerpawlib.v2 import DummyVehicle

vehicle = await DummyVehicle.connect()
# goto_coordinates, can_takeoff, etc. all succeed silently
```

## Error Handling

All v2 exceptions derive from `AerpawlibError`. Each carries `message`, `code`, `severity` (`"warning"`, `"error"`, `"critical"`), and optionally `original_error` (the underlying exception).

```python
from aerpawlib.v2 import TakeoffError, NavigationError, AerpawlibError

try:
    await drone.takeoff(10)
except TakeoffError as e:
    print(e.code, e.message)  # TAKEOFF_ERROR, ...
except AerpawlibError as e:
    print(e.severity, e)
```

### Exception Hierarchy

```
AerpawlibError
├── AerpawConnectionError
│   ├── ConnectionTimeoutError   # no heartbeat within timeout
│   ├── HeartbeatLostError       # heartbeat lost mid-flight (severity: critical)
│   └── PortInUseError           # gRPC port conflict
├── CommandError
│   ├── ArmError                 # arm command rejected
│   ├── DisarmError              # disarm command rejected
│   ├── TakeoffError             # takeoff failed
│   ├── LandingError             # landing failed
│   ├── NavigationError          # goto failed or timed out
│   ├── VelocityError            # set_velocity failed
│   └── RTLError                 # return_to_launch failed
├── StateError
│   ├── NotArmableError          # arm attempted while vehicle not armable
│   ├── NotConnectedError        # command attempted on disconnected vehicle
│   └── UnexpectedDisarmError    # vehicle disarmed mid-experiment (severity: critical)
├── RunnerError
│   ├── NoEntrypointError        # BasicRunner missing @entrypoint
│   ├── NoInitialStateError      # StateMachine missing first=True state
│   ├── MultipleInitialStatesError
│   ├── InvalidStateError        # state transition returned unknown state name
│   └── InvalidStateNameError    # empty state name passed to @state
└── PlanError                    # .plan file cannot be parsed
```

`UnexpectedDisarmError` is raised automatically by `BasicRunner` and `StateMachine` when the vehicle disarms during a mission (e.g. motor failsafe), terminating the experiment cleanly.