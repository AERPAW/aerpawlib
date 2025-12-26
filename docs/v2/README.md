# aerpawlib v2 API Documentation

The v2 API is the **recommended** API for new projects. It provides a modern, Pythonic interface for vehicle control using MAVSDK with enhanced features including:

- **Clean property-based state access** (`drone.state.heading`, `drone.battery.voltage`)
- **Intuitive Coordinate-based navigation**
- **Async-first design** with native MAVSDK backend
- **CommandHandle for non-blocking operations** with progress tracking
- **Structured exception hierarchy** for granular error handling
- **Context manager support** for clean resource management
- **Built-in safety features** with configurable limits, pre-flight checks, and battery failsafe

## Requirements

- Python 3.8+
- MAVSDK-Python (`pip install mavsdk`)

## Documentation Index

- [README](README.md) - This file, full API reference
- [CommandHandle Guide](command_handle.md) - Non-blocking operations
- [Safety Features](safety.md) - Safety limits, pre-flight checks, battery failsafe
- [Migration Guide](migration.md) - Migrating from legacy/v1

## Quick Start

```python
from aerpawlib.v2 import Drone, Coordinate, BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.connect()
        await drone.arm()  # Runs pre-flight checks automatically
        await drone.takeoff(altitude=10)
        await drone.goto(coordinates=Coordinate(35.7275, -78.6960, 10, "Target"))
        await drone.land()
```

## Quick Start with Safety Configuration

```python
from aerpawlib.v2 import Drone, SafetyLimits, BasicRunner, entrypoint

class SafeMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        # Use restrictive limits for beginners
        drone = Drone("udp://:14540", safety_limits=SafetyLimits.restrictive())
        await drone.connect()
        
        # Pre-flight checks run automatically
        await drone.arm()
        await drone.takeoff(altitude=5)
        await drone.land()
```

## Core Concepts

### Connection

```python
from aerpawlib.v2 import Drone

async with Drone("udp://:14540") as drone:
    await drone.arm()
    await drone.takeoff(altitude=10)
    await drone.land()
    
# Or explicit connect/disconnect
drone = Drone("udp://:14540")
await drone.connect()
# ... mission ...
await drone.disconnect()
```

### State Access

The v2 API provides clean property-based access to vehicle state:

```python
# Position and navigation
position = drone.position           # Coordinate
altitude = drone.altitude           # float (meters above home)
heading = drone.heading             # float (degrees)
velocity = drone.velocity           # VectorNED

# State container with all telemetry
state = drone.state
print(f"Heading: {state.heading}°")
print(f"Groundspeed: {state.groundspeed} m/s")
print(f"Flight mode: {state.flight_mode}")
print(f"In air: {state.is_in_air}")

# GPS information
gps = drone.gps
print(f"Satellites: {gps.satellites}")
print(f"Fix quality: {gps.quality}")

# Battery information
battery = drone.battery
print(f"Voltage: {battery.voltage}V")
print(f"Charge: {battery.percentage}%")
print(f"Low battery: {battery.is_low}")
```

### Runners

| Runner | Description |
|--------|-------------|
| `BasicRunner` | Simple entry point execution with `@entrypoint` |
| `StateMachine` | State-based execution with `@state`, `@timed_state`, `@background`, `@at_init` |

---

## API Reference

### Vehicle Properties

| Property | Type | Description |
|----------|------|-------------|
| `position` | `Coordinate` | Current position |
| `altitude` | `float` | Altitude above home (meters) |
| `heading` | `float` | Current heading (degrees, 0=North) |
| `velocity` | `VectorNED` | Current velocity |
| `is_in_air` | `bool` | True if airborne |
| `state` | `StateContainer` | Full telemetry state |
| `gps` | `GPSContainer` | GPS information |
| `battery` | `BatteryContainer` | Battery information |
| `info` | `InfoContainer` | Vehicle information |

### Connection Methods

#### `await connect(timeout=30.0, auto_reconnect=False, retry_count=3, retry_delay=2.0)`
Connect to the vehicle.

```python
await drone.connect(timeout=30, auto_reconnect=True)
```

#### `await disconnect()`
Disconnect and clean up resources.

```python
await drone.disconnect()
```

### Arming & Takeoff

#### `await arm(force=False) -> bool`
Arm the vehicle.

```python
await drone.arm()
await drone.arm(force=True)  # Bypass pre-arm checks (dangerous!)
```

#### `await disarm(force=False) -> bool`
Disarm the vehicle.

```python
await drone.disarm()
```

#### `await takeoff(altitude=5.0, wait=True, timeout=60.0) -> Optional[CommandHandle]`
Take off to specified altitude.

```python
# Blocking (default)
await drone.takeoff(altitude=10)

# Non-blocking with handle
handle = await drone.takeoff(altitude=10, wait=False)
while handle.is_running:
    print(f"Altitude: {drone.altitude}m")
    await asyncio.sleep(0.5)
```

### Navigation

#### `await goto(...) -> Optional[CommandHandle]`
Navigate to a location.

| Parameter | Type | Description |
|-----------|------|-------------|
| `latitude` | `float` | Target latitude |
| `longitude` | `float` | Target longitude |
| `altitude` | `float` | Target altitude (optional) |
| `coordinates` | `Coordinate` | Target as Coordinate object |
| `tolerance` | `float` | Acceptance radius (meters, default: 2) |
| `speed` | `float` | Ground speed (m/s, optional) |
| `heading` | `float` | Target heading (optional) |
| `timeout` | `float` | Max time (seconds, default: 300) |
| `wait` | `bool` | Block until complete (default: True) |

```python
# Using coordinates
await drone.goto(latitude=35.7, longitude=-78.6)
await drone.goto(coordinates=Coordinate(35.7, -78.6, 10, "Target"))

# Non-blocking with progress
handle = await drone.goto(coordinates=target, wait=False)
while handle.is_running:
    print(f"Distance: {handle.progress['distance']:.1f}m")
    await asyncio.sleep(1)
```

#### `await hold()`
Hold current position.

```python
await drone.hold()
```

#### `await rtl(wait=True, timeout=300.0) -> Optional[CommandHandle]`
Return to launch position.

```python
await drone.rtl()
```

#### `await land(wait=True, timeout=120.0) -> Optional[CommandHandle]`
Land at current position.

```python
await drone.land()
```

### Heading & Velocity

#### `await set_heading(degrees, blocking=True, timeout=30.0) -> Optional[CommandHandle]`
Set vehicle heading.

```python
await drone.set_heading(90)  # Face east
handle = await drone.set_heading(180, blocking=False)
```

#### `await point_at(target: Optional[Coordinate] = None)`
Point at a target coordinate (or direction of travel if None).

```python
await drone.point_at(target_coordinate)
```

#### `await set_velocity(velocity, heading=None, duration=None, wait=True) -> Optional[CommandHandle]`
Set velocity in NED frame.

```python
# Continuous velocity
await drone.set_velocity(VectorNED(5, 0, 0))  # 5 m/s north

# Timed velocity
await drone.set_velocity(VectorNED(5, 0, 0), duration=10)

# Non-blocking timed velocity
handle = await drone.set_velocity(VectorNED(5, 0, 0), duration=10, wait=False)
```

#### `await set_groundspeed(speed)`
Set maximum ground speed for goto operations.

```python
await drone.set_groundspeed(10)  # 10 m/s
```

#### `await set_altitude(altitude, tolerance=0.5)`
Change altitude while maintaining position.

```python
await drone.set_altitude(20)
```

### Movement Helpers

#### `await move_in_direction(distance, degrees, speed=5.0)`
Move in a specified direction.

```python
await drone.move_in_direction(50, 90, speed=5)  # 50m east at 5 m/s
```

#### `await move_in_current_direction(distance, speed=5.0)`
Move in current heading direction.

```python
await drone.move_in_current_direction(100)  # 100m forward
```

#### `await move_towards(target, distance, speed=5.0)`
Move towards a target by a specified distance.

```python
await drone.move_towards(target_coord, 50)  # Move 50m towards target
```

### Orbit

#### `await orbit(center, radius, speed=5.0, clockwise=True, revolutions=1.0, wait=True) -> Optional[CommandHandle]`
Orbit around a center point.

```python
center = drone.position + VectorNED(50, 0, 0)  # 50m north
await drone.orbit(center=center, radius=30, revolutions=2)

# Non-blocking with progress
handle = await drone.orbit(center=center, radius=30, revolutions=2, wait=False)
while handle.is_running:
    print(f"Progress: {handle.progress['progress_percent']:.1f}%")
    await asyncio.sleep(1)
```

### Abort

#### `await abort(rtl=True)`
Abort current operation.

```python
await drone.abort()        # Return to launch
await drone.abort(rtl=False)  # Hold position
```

#### `reset_abort()`
Reset abort flag to allow new operations.

```python
drone.reset_abort()
```

---

## CommandHandle

CommandHandle enables non-blocking command execution with progress tracking, cancellation, and result inspection.

### Creating a CommandHandle

Pass `wait=False` to any supported command:

```python
handle = await drone.goto(coordinates=target, wait=False)
handle = await drone.takeoff(altitude=10, wait=False)
handle = await drone.land(wait=False)
handle = await drone.orbit(center=center, radius=50, wait=False)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_running` | `bool` | True if command is executing |
| `is_complete` | `bool` | True if finished (success/fail/cancel) |
| `succeeded` | `bool` | True if completed successfully |
| `was_cancelled` | `bool` | True if cancelled |
| `timed_out` | `bool` | True if timed out |
| `elapsed_time` | `float` | Seconds since command started |
| `time_remaining` | `float` | Seconds until timeout (if set) |
| `progress` | `dict` | Command-specific progress info |
| `error` | `Exception` | Error if failed, None otherwise |

### Methods

#### `await wait(timeout=None) -> CommandHandle`
Wait for command completion.

```python
await handle.wait()
await handle.wait(timeout=30)  # Additional timeout
```

#### `await cancel(execute_cancel_action=True) -> bool`
Cancel the command.

```python
success = await handle.cancel()
```

#### `result() -> CommandResult`
Get detailed result (only after completion).

```python
result = handle.result()
print(f"Duration: {result.duration}s")
print(f"Status: {result.status}")
```

### Awaiting Handles

You can await a handle directly:

```python
handle = await drone.goto(coordinates=target, wait=False)
# ... do other things ...
await handle  # Wait for completion
```

### Progress Information

Each command provides specific progress data:

| Command | Progress Fields |
|---------|-----------------|
| `goto` | `distance`, `target`, `tolerance` |
| `takeoff` | `current_altitude`, `target_altitude`, `altitude_remaining` |
| `land` | `current_altitude`, `landed_state`, `armed` |
| `rtl` | `distance_to_home`, `current_altitude`, `landed_state` |
| `set_heading` | `current_heading`, `target_heading`, `heading_diff` |
| `set_velocity` | `elapsed`, `duration`, `time_remaining` |
| `orbit` | `revolutions_completed`, `progress_percent`, `time_remaining` |

### Example: Progress Monitoring

```python
handle = await drone.goto(coordinates=target, wait=False)

while handle.is_running:
    progress = handle.progress
    print(f"Distance: {progress.get('distance', 0):.1f}m")
    print(f"Elapsed: {handle.elapsed_time:.1f}s")
    await asyncio.sleep(1)

if handle.succeeded:
    print("Arrived!")
elif handle.was_cancelled:
    print("Cancelled")
elif handle.timed_out:
    print("Timed out")
```

---

## Types

### Coordinate

Represents a geographic position.

```python
from aerpawlib.v2 import Coordinate

# Create
pos = Coordinate(latitude=35.7, longitude=-78.6, altitude=10, name="Home")
pos = Coordinate(35.7, -78.6, 10)  # Positional args

# Properties
lat = pos.latitude  # or pos.lat
lon = pos.longitude  # or pos.lon
alt = pos.altitude  # or pos.alt

# Distance and bearing
dist = pos.distance_to(other)      # 3D distance in meters
ground = pos.ground_distance_to(other)  # 2D distance
bearing = pos.bearing_to(other)    # Degrees (0=North)

# Offset operations
new_pos = pos.offset_by(VectorNED(100, 50, -10))  # Move by vector
new_pos = pos + VectorNED(100, 0, 0)  # Operator syntax

# Vector between coordinates
vector = pos.vector_to(other)  # VectorNED
```

### VectorNED

Represents a 3D vector in North-East-Down frame.

```python
from aerpawlib.v2 import VectorNED

vec = VectorNED(north=5.0, east=3.0, down=0.0)

# Magnitude
mag = vec.magnitude()               # 3D magnitude
horiz = vec.magnitude(ignore_vertical=True)  # 2D magnitude

# Operations
normalized = vec.normalize()        # Unit vector
rotated = vec.rotate_by_angle(45)   # Rotate by degrees
heading = vec.heading()             # Compass heading

# Arithmetic
result = vec1 + vec2
result = vec1 - vec2
result = vec * 2.0
result = -vec
```

### Waypoint

Represents a waypoint with additional parameters.

```python
from aerpawlib.v2 import Waypoint, Coordinate

wp = Waypoint(
    coordinate=Coordinate(35.7, -78.6, 10),
    speed=5.0,              # Optional speed override
    acceptance_radius=2.0,  # Arrival tolerance
    hold_time=5.0,          # Time to hover at waypoint
    name="WP1"
)
```

### Enums

```python
from aerpawlib.v2 import FlightMode, LandedState

# Flight modes
FlightMode.MANUAL
FlightMode.HOLD
FlightMode.MISSION
FlightMode.RETURN_TO_LAUNCH
FlightMode.LAND
FlightMode.TAKEOFF
FlightMode.OFFBOARD

# Landed states
LandedState.ON_GROUND
LandedState.IN_AIR
LandedState.TAKING_OFF
LandedState.LANDING
```

---

## Decorators

### `@entrypoint`
Mark a method as the entry point for `BasicRunner`.

```python
from aerpawlib.v2 import BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=10)
```

### `@state(name, first=False)`
Define a state for `StateMachine`.

```python
from aerpawlib.v2 import StateMachine, state

class MyMission(StateMachine):
    @state("takeoff", first=True)
    async def takeoff(self, drone: Drone):
        await drone.takeoff(altitude=10)
        return "navigate"  # Next state name
```

### `@timed_state(name, duration, loop=False, first=False)`
Define a timed state.

```python
@timed_state("monitor", duration=30, loop=True)
async def monitor(self, drone: Drone):
    print(f"Altitude: {drone.altitude}m")
    return "land"  # Transition after 30 seconds
```

### `@background`
Run a function in parallel with the state machine.

```python
@background
async def telemetry_logger(self, drone: Drone):
    while True:
        print(f"Battery: {drone.battery.percentage}%")
        await asyncio.sleep(5)
```

### `@at_init`
Run initialization before mission starts.

```python
@at_init
async def setup(self, drone: Drone):
    self.waypoints = [...]
```

---

## Event Callbacks

Register callbacks for vehicle events:

```python
drone.on("on_arm", lambda: print("Armed!"))
drone.on("on_disarm", lambda: print("Disarmed!"))
drone.on("on_low_battery", lambda: print("Low battery!"))
drone.on("on_critical_battery", lambda: print("Critical battery!"))
drone.on("on_mode_change", lambda old, new: print(f"Mode: {old} → {new}"))
drone.on("on_connect", lambda: print("Connected"))
drone.on("on_disconnect", lambda: print("Disconnected"))

# Remove callback
drone.off("on_arm", callback_func)
```

---

## Flight Recording

Record telemetry during flight:

```python
drone.start_recording(interval=0.1)  # 10 Hz
# ... fly mission ...
drone.stop_recording()
drone.save_flight_log("flight.json", format="json")
drone.save_flight_log("flight.csv", format="csv")

# Access data directly
log_data = drone.get_flight_log()
```

---

## Exceptions

The v2 API provides a structured exception hierarchy:

```python
from aerpawlib.v2 import (
    AerpawlibError,          # Base exception
    ConnectionError,         # Connection failures
    ConnectionTimeoutError,  # Connection timeout
    HeartbeatLostError,      # Lost heartbeat
    CommandError,            # Command failures
    ArmError,                # Arming failed
    TakeoffError,            # Takeoff failed
    LandingError,            # Landing failed
    NavigationError,         # Navigation failed
    GotoTimeoutError,        # Goto timed out
    TakeoffTimeoutError,     # Takeoff timed out
    LandingTimeoutError,     # Landing timed out
    AbortError,              # Operation aborted
    CommandCancelledError,   # Command cancelled via handle
    GeofenceViolationError,  # Geofence violation
)

try:
    await drone.goto(coordinates=target, timeout=60)
except GotoTimeoutError as e:
    print(f"Goto timed out: {e.distance_remaining}m remaining")
except NavigationError as e:
    print(f"Navigation failed: {e.reason}")
```

---

## Examples

### Basic Flight

```python
from aerpawlib.v2 import Drone, Coordinate, BasicRunner, entrypoint

class SimpleFlight(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.connect()
        await drone.arm()
        await drone.takeoff(altitude=10)
        
        waypoints = [
            Coordinate(35.7275, -78.6960, 10, "WP1"),
            Coordinate(35.7280, -78.6955, 15, "WP2"),
        ]
        
        for wp in waypoints:
            await drone.goto(coordinates=wp)
        
        await drone.land()
```

### State Machine

```python
from aerpawlib.v2 import Drone, Coordinate, StateMachine, state, background, at_init

class PatrolMission(StateMachine):
    @at_init
    async def setup(self, drone: Drone):
        self.waypoints = [
            Coordinate(35.7275, -78.6960, 15),
            Coordinate(35.7280, -78.6955, 15),
        ]
        self.current_wp = 0
    
    @state("takeoff", first=True)
    async def takeoff(self, drone: Drone):
        await drone.connect()
        await drone.arm()
        await drone.takeoff(altitude=15)
        return "patrol"
    
    @state("patrol")
    async def patrol(self, drone: Drone):
        if self.current_wp >= len(self.waypoints):
            return "rtl"
        await drone.goto(coordinates=self.waypoints[self.current_wp])
        self.current_wp += 1
        return "patrol"
    
    @state("rtl")
    async def return_home(self, drone: Drone):
        await drone.rtl()
        return None
    
    @background
    async def battery_monitor(self, drone: Drone):
        while True:
            if drone.battery.is_low:
                print("Low battery!")
            await asyncio.sleep(5)
```

### Non-blocking Operations

```python
from aerpawlib.v2 import Drone, Coordinate, BasicRunner, entrypoint

class NonBlockingDemo(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.connect()
        await drone.arm()
        await drone.takeoff(altitude=10)
        
        # Start goto without waiting
        target = Coordinate(35.7275, -78.6960, 10)
        handle = await drone.goto(coordinates=target, wait=False)
        
        # Monitor progress
        while handle.is_running:
            print(f"Distance: {handle.progress['distance']:.1f}m")
            print(f"Elapsed: {handle.elapsed_time:.1f}s")
            await asyncio.sleep(1)
        
        if handle.succeeded:
            print("Arrived!")
        
        await drone.land()
```

---

## Migration Guide

See [migration.md](migration.md) for detailed migration instructions from legacy or v1.

### Quick Comparison

| Legacy/v1 | v2 |
|-----------|-----|
| `drone.goto_coordinates(coord)` | `drone.goto(coordinates=coord)` |
| `drone.position.alt` | `drone.altitude` |
| `drone.battery.level` | `drone.battery.percentage` |
| `drone.set_heading(90)` | `drone.set_heading(90)` |
| Blocking only | `wait=False` for non-blocking |
| Generic exceptions | Structured exception hierarchy |

