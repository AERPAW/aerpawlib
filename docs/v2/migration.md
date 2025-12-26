# Migration Guide to aerpawlib v2

This guide helps you migrate from the legacy or v1 API to the modern v2 API.

## Why Migrate?

The v2 API offers significant improvements:

| Feature | Legacy/v1 | v2 |
|---------|-----------|-----|
| Backend | DroneKit/MAVSDK | MAVSDK native |
| State access | Method calls | Properties (`drone.altitude`) |
| Non-blocking ops | Not supported | CommandHandle |
| Error handling | Generic exceptions | Structured hierarchy |
| Resource cleanup | Manual | Context managers |
| Progress tracking | Not available | Built-in |
| Event callbacks | Limited | Comprehensive |
| Flight recording | Manual | Built-in |

---

## Migration Steps

### 1. Update Imports

```python
# Before (legacy)
from aerpawlib.legacy import Drone, Coordinate, VectorNED, BasicRunner, entrypoint

# Before (v1)
from aerpawlib.v1 import Drone, Coordinate, VectorNED, BasicRunner, entrypoint

# After (v2)
from aerpawlib.v2 import Drone, Coordinate, VectorNED, BasicRunner, entrypoint
```

### 2. Add Connection Call

The v2 API requires an explicit `connect()` call:

```python
# Before (legacy/v1)
drone = Drone("udp://:14540")
# Connection happens in constructor

# After (v2)
drone = Drone("udp://:14540")
await drone.connect()

# Or use context manager (recommended)
async with Drone("udp://:14540") as drone:
    # Automatically connects and disconnects
    pass
```

### 3. Update Navigation Methods

```python
# Before (legacy/v1)
await drone.goto_coordinates(Coordinate(35.7, -78.6, 10), tolerance=2)

# After (v2) - multiple options
await drone.goto(coordinates=Coordinate(35.7, -78.6, 10), tolerance=2)
await drone.goto(latitude=35.7, longitude=-78.6, altitude=10, tolerance=2)
```

### 4. Update Property Access

```python
# Before (legacy/v1)
alt = drone.position.alt
bat = drone.battery.level

# After (v2)
alt = drone.altitude  # Shortcut property
alt = drone.state.relative_altitude  # Full state access
bat = drone.battery.percentage
```

### 5. Add Explicit Arming

```python
# Before (legacy/v1) - arming often implicit
await drone.takeoff(10)

# After (v2) - explicit arming recommended
await drone.arm()
await drone.takeoff(altitude=10)
```

---

## API Mapping

### Vehicle Methods

| Legacy/v1 | v2 |
|-----------|-----|
| `goto_coordinates(coord, tol)` | `goto(coordinates=coord, tolerance=tol)` |
| `set_heading(deg)` | `set_heading(deg)` |
| `set_velocity(vec, dur)` | `set_velocity(vec, duration=dur)` |
| `set_groundspeed(spd)` | `set_groundspeed(spd)` |
| `takeoff(alt)` | `takeoff(altitude=alt)` |
| `land()` | `land()` |
| `set_armed(True)` | `arm()` |
| `set_armed(False)` | `disarm()` |
| `await_ready_to_move()` | Handled automatically |
| `done_moving()` | Use `CommandHandle.is_complete` |

### Properties

| Legacy/v1 | v2 |
|-----------|-----|
| `drone.position` | `drone.position` |
| `drone.position.alt` | `drone.altitude` |
| `drone.heading` | `drone.heading` |
| `drone.velocity` | `drone.velocity` |
| `drone.battery.level` | `drone.battery.percentage` |
| `drone.battery.voltage` | `drone.battery.voltage` |
| `drone.gps.fix_type` | `drone.gps.fix_type` |
| `drone.gps.satellites_visible` | `drone.gps.satellites` |
| `drone.armed` | `drone._armed` (internal) |
| `drone.connected` | Check after `connect()` |
| `drone.home_coords` | `drone._home` |

### Utility Types

| Legacy/v1 | v2 |
|-----------|-----|
| `Coordinate(lat, lon, alt)` | `Coordinate(lat, lon, alt, name)` |
| `coord.distance(other)` | `coord.distance_to(other)` |
| `coord.ground_distance(other)` | `coord.ground_distance_to(other)` |
| `coord.bearing(other)` | `coord.bearing_to(other)` |
| `VectorNED(n, e, d)` | `VectorNED(n, e, d)` |
| `vec.hypot()` | `vec.magnitude()` |
| `vec.norm()` | `vec.normalize()` |

### Decorators

Decorators work the same way:

```python
# All decorators work identically
@entrypoint
@state("name", first=True)
@timed_state("name", duration=10, loop=True)
@background
@at_init  # New in v2
```

---

## Full Migration Example

### Before (Legacy/v1)

```python
from aerpawlib.legacy import Drone, Coordinate, VectorNED, BasicRunner, entrypoint
import asyncio

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        # Takeoff
        await drone.takeoff(10)
        
        # Navigate to waypoints
        waypoints = [
            Coordinate(35.7275, -78.6960, 15),
            Coordinate(35.7280, -78.6955, 20),
        ]
        
        for wp in waypoints:
            await drone.goto_coordinates(wp, tolerance=2)
        
        # Set heading
        await drone.set_heading(90)
        
        # Velocity control
        await drone.set_velocity(VectorNED(5, 0, 0), duration=10)
        
        # Land
        await drone.land()
```

### After (v2)

```python
from aerpawlib.v2 import Drone, Coordinate, VectorNED, BasicRunner, entrypoint
import asyncio

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        # Connect and arm
        await drone.connect()
        await drone.arm()
        
        # Takeoff
        await drone.takeoff(altitude=10)
        
        # Navigate to waypoints
        waypoints = [
            Coordinate(35.7275, -78.6960, 15, "WP1"),
            Coordinate(35.7280, -78.6955, 20, "WP2"),
        ]
        
        for wp in waypoints:
            await drone.goto(coordinates=wp, tolerance=2)
        
        # Set heading
        await drone.set_heading(90)
        
        # Velocity control
        await drone.set_velocity(VectorNED(5, 0, 0), duration=10)
        
        # Land
        await drone.land()
```

### With v2 Enhancements

```python
from aerpawlib.v2 import (
    Drone, Coordinate, VectorNED, BasicRunner, entrypoint,
    GotoTimeoutError, CommandCancelledError
)
import asyncio

class EnhancedMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        # Context manager for automatic cleanup
        async with Drone("udp://:14540") as drone:
            await drone.arm()
            
            # Non-blocking takeoff with progress
            handle = await drone.takeoff(altitude=10, wait=False)
            while handle.is_running:
                print(f"Altitude: {drone.altitude:.1f}m")
                await asyncio.sleep(0.5)
            
            # Navigate with error handling
            waypoints = [
                Coordinate(35.7275, -78.6960, 15, "WP1"),
                Coordinate(35.7280, -78.6955, 20, "WP2"),
            ]
            
            for wp in waypoints:
                try:
                    handle = await drone.goto(coordinates=wp, wait=False)
                    while handle.is_running:
                        dist = handle.progress.get('distance', 0)
                        print(f"→ {wp.name}: {dist:.1f}m remaining")
                        await asyncio.sleep(1)
                except GotoTimeoutError as e:
                    print(f"Timeout at {wp.name}: {e.distance_remaining}m left")
                    break
            
            # Event callbacks
            drone.on("on_low_battery", lambda: print("Low battery!"))
            
            # Flight recording
            drone.start_recording()
            await drone.orbit(center=drone.position, radius=50, revolutions=1)
            drone.stop_recording()
            drone.save_flight_log("orbit.json")
            
            await drone.land()
```

---

## Handling Breaking Changes

### Connection Strings

Connection strings remain the same MAVSDK format:

```python
"udp://:14540"          # UDP on default port
"udp://192.168.1.1:14540"  # UDP to specific host
"serial:///dev/ttyUSB0:57600"  # Serial
```

### Coordinate Changes

The v2 Coordinate has an optional `name` parameter:

```python
# Legacy/v1
coord = Coordinate(35.7, -78.6, 10)

# v2 - name is optional
coord = Coordinate(35.7, -78.6, 10)
coord = Coordinate(35.7, -78.6, 10, "Home")
coord = Coordinate(latitude=35.7, longitude=-78.6, altitude=10, name="Home")
```

### Exception Handling

Replace generic exception handling with specific types:

```python
# Before
try:
    await drone.goto_coordinates(target)
except Exception as e:
    print(f"Failed: {e}")

# After
from aerpawlib.v2 import GotoTimeoutError, NavigationError, AbortError

try:
    await drone.goto(coordinates=target)
except GotoTimeoutError as e:
    print(f"Timed out, {e.distance_remaining}m remaining")
except NavigationError as e:
    print(f"Navigation failed: {e.reason}")
except AbortError:
    print("Mission aborted")
```

---

## Best Practices for v2

### 1. Use Context Managers

```python
async with Drone("udp://:14540") as drone:
    # Automatic connect/disconnect
    await drone.arm()
    # ...
```

### 2. Prefer Non-blocking for Long Operations

```python
# For operations that take time, consider non-blocking
handle = await drone.goto(coordinates=far_target, wait=False)

# Can do other things while waiting
while handle.is_running:
    log_telemetry()
    await asyncio.sleep(1)
```

### 3. Use Structured Exceptions

```python
from aerpawlib.v2 import GotoTimeoutError, NavigationError

try:
    await drone.goto(coordinates=target, timeout=60)
except GotoTimeoutError:
    await drone.rtl()  # Return home on timeout
```

### 4. Register Event Callbacks

```python
drone.on("on_low_battery", handle_low_battery)
drone.on("on_critical_battery", emergency_land)
```

### 5. Enable Flight Recording for Debugging

```python
drone.start_recording(interval=0.1)
# ... mission ...
drone.save_flight_log("mission.json")
```

---

## Getting Help

- Check the [v2 API Reference](README.md) for detailed documentation
- Review [examples/v2/](../../examples/v2/) for working examples
- Open an issue for migration problems

