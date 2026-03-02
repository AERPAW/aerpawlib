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
aerpawlib --api-version v2 --script my_script --vehicle drone --conn udpin://127.0.0.1:14550
```

## Architecture

- No background threads for MAVSDK. All commands use direct `await`.
- Subscriptions update plain attributes; no ThreadSafeValue.
- Runners use config dataclass (`BasicRunnerConfig`, `StateMachineConfig`) or decorators.
- Non-blocking commands with `progress`, `cancel()`, and `wait_done()`.

## Key Types

| Type | Purpose |
|------|---------|
| `Coordinate` | WGS84 position (lat, lon, alt) |
| `VectorNED` | NED displacement (north, east, down) in meters |
| `Battery`, `GPSInfo`, `Attitude` | Telemetry dataclasses |
| `VehicleTask` | Non-blocking command with progress |

## Vehicle API

### Connection
```python
vehicle = await Drone.connect("udpin://127.0.0.1:14550")
# With safety checker:
from aerpawlib.v2.safety import SafetyCheckerClient
vehicle = await Drone.connect("udpin://127.0.0.1:14550", safety=SafetyCheckerClient("127.0.0.1", 14580))
```

### Commands (blocking)
```python
await drone.takeoff(altitude=10)
await drone.goto_coordinates(target, tolerance=2)
await drone.set_heading(90)
await drone.land()
await drone.return_to_launch()
```

### Non-blocking goto
```python
handle = await drone.goto_coordinates(target, blocking=False)
print(handle.progress)
await handle.wait_done()
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
```

### ZmqStateMachine

State machine with remote ZMQ control:

```python
from aerpawlib.v2 import ZmqStateMachine, Drone, state, expose_zmq

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
```

Run with `--zmq-identifier` and `--zmq-proxy-server`. Start the ZMQ proxy first: `aerpawlib --run-proxy`.

### Config Dataclass

Runners can use explicit config instead of decorators:

```python
from aerpawlib.v2 import BasicRunner, BasicRunnerConfig

class MyMission(BasicRunner):
    config = BasicRunnerConfig(entrypoint="run")
    async def run(self, drone):
        ...
```

## QGroundControl Plan Files

```python
from aerpawlib.v2.plan import read_from_plan, get_location_from_waypoint

waypoints = read_from_plan("mission.plan")
for wp in waypoints:
    coord = get_location_from_waypoint(wp)
    await drone.goto_coordinates(coord)
```

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
```

## Safety Integration

Pass a safety client (`SafetyCheckerClient` or `NoOpSafetyChecker`) to `connect(safety=...)`. The vehicle constructor stores it for `can_takeoff`, `can_goto`, `can_land`. When running via CLI, aerpawlib builds the safety client and passes it automatically (see [Safety — Automatic Setup](safety.md#automatic-setup-via-cli-safety-checker-port)).

```python
from aerpawlib.v2.safety import SafetyCheckerClient

client = SafetyCheckerClient("127.0.0.1", 14580)
drone = await Drone.connect("udpin://127.0.0.1:14550", safety=client)
ok, msg = await drone.can_takeoff(10)
```

Or use the CLI: `--safety-checker-port 14580` (in AERPAW, defaults to 14580; outside AERPAW, optional with passthrough on failure).