# CommandHandle Guide

CommandHandle is a powerful feature in the v2 API that enables non-blocking command execution with progress tracking, cancellation support, and detailed result inspection.

## Overview

When you call commands like `goto()`, `takeoff()`, `land()`, etc. with `wait=False`, they return a `CommandHandle` instead of blocking until completion.

```python
# Blocking (default)
await drone.goto(coordinates=target)  # Returns when arrived

# Non-blocking
handle = await drone.goto(coordinates=target, wait=False)  # Returns immediately
# ... do other things ...
await handle  # Wait for completion when ready
```

## Supported Commands

The following commands support `CommandHandle`:

| Command | `wait` Parameter | Progress Fields |
|---------|------------------|-----------------|
| `goto()` | `wait=False` | `distance`, `target`, `tolerance` |
| `takeoff()` | `wait=False` | `current_altitude`, `target_altitude`, `altitude_remaining` |
| `land()` | `wait=False` | `current_altitude`, `landed_state`, `armed` |
| `rtl()` | `wait=False` | `distance_to_home`, `current_altitude`, `landed_state` |
| `set_heading()` | `blocking=False` | `current_heading`, `target_heading`, `heading_diff` |
| `set_velocity()` | `wait=False` (with `duration`) | `elapsed`, `duration`, `time_remaining` |
| `orbit()` | `wait=False` | `revolutions_completed`, `progress_percent`, `time_remaining` |

## Creating Handles

```python
from aerpawlib.v2 import Drone, Coordinate

drone = Drone("udp://:14540")
await drone.connect()
await drone.arm()

# Takeoff handle
takeoff_handle = await drone.takeoff(altitude=10, wait=False)

# Goto handle
target = Coordinate(35.7, -78.6, 10)
goto_handle = await drone.goto(coordinates=target, wait=False)

# Orbit handle
orbit_handle = await drone.orbit(center=target, radius=50, wait=False)

# Land handle
land_handle = await drone.land(wait=False)
```

## Checking Status

### Properties

```python
handle = await drone.goto(coordinates=target, wait=False)

# Status checks
handle.is_pending    # True if not yet started
handle.is_running    # True if currently executing
handle.is_complete   # True if finished (any result)
handle.succeeded     # True if completed successfully
handle.was_cancelled # True if cancelled
handle.timed_out     # True if timed out

# Timing
handle.elapsed_time   # Seconds since start
handle.time_remaining # Seconds until timeout (or None)

# Error
handle.error  # Exception if failed, None otherwise
```

### Status Enum

```python
from aerpawlib.v2 import CommandStatus

handle.status == CommandStatus.PENDING
handle.status == CommandStatus.RUNNING
handle.status == CommandStatus.COMPLETED
handle.status == CommandStatus.FAILED
handle.status == CommandStatus.CANCELLED
handle.status == CommandStatus.TIMED_OUT
```

## Monitoring Progress

Each command provides specific progress information via `handle.progress`:

### Goto Progress

```python
handle = await drone.goto(coordinates=target, wait=False)

while handle.is_running:
    progress = handle.progress
    print(f"Distance: {progress['distance']:.1f}m")
    print(f"Target: {progress['target']}")
    print(f"Tolerance: {progress['tolerance']}m")
    await asyncio.sleep(1)
```

### Takeoff Progress

```python
handle = await drone.takeoff(altitude=20, wait=False)

while handle.is_running:
    progress = handle.progress
    print(f"Current: {progress['current_altitude']:.1f}m")
    print(f"Target: {progress['target_altitude']}m")
    print(f"Remaining: {progress['altitude_remaining']:.1f}m")
    await asyncio.sleep(0.5)
```

### Orbit Progress

```python
handle = await drone.orbit(center=center, radius=50, revolutions=2, wait=False)

while handle.is_running:
    progress = handle.progress
    print(f"Revolutions: {progress['revolutions_completed']:.2f} / {progress['target_revolutions']}")
    print(f"Progress: {progress['progress_percent']:.1f}%")
    print(f"Time remaining: {progress['time_remaining']:.1f}s")
    await asyncio.sleep(1)
```

## Waiting for Completion

### Direct Await

```python
handle = await drone.goto(coordinates=target, wait=False)

# Do other things...
check_battery()
log_position()

# Wait for completion
await handle  # Blocks until complete
```

### Wait Method

```python
handle = await drone.goto(coordinates=target, wait=False)

# Wait with additional timeout
await handle.wait(timeout=30)

# Chaining is supported
await handle.wait().result()  # Get result after waiting
```

### Error Handling on Wait

```python
from aerpawlib.v2 import CommandCancelledError, GotoTimeoutError

handle = await drone.goto(coordinates=target, wait=False)

try:
    await handle.wait()
except CommandCancelledError:
    print("Command was cancelled")
except GotoTimeoutError as e:
    print(f"Timed out, {e.distance_remaining}m remaining")
```

## Cancelling Commands

```python
handle = await drone.goto(coordinates=far_target, wait=False)

# Wait a bit
await asyncio.sleep(10)

# Cancel the command
cancelled = await handle.cancel()

if cancelled:
    print("Command cancelled, drone is holding position")
else:
    print("Command already completed")

# Check status
print(f"Was cancelled: {handle.was_cancelled}")
```

### Cancel with Custom Action

By default, cancelling a `goto` calls `hold()`. You can disable this:

```python
# Cancel without executing stop action
await handle.cancel(execute_cancel_action=False)
```

## Getting Results

After completion, you can get detailed results:

```python
from aerpawlib.v2 import CommandResult

handle = await drone.goto(coordinates=target, wait=False)
await handle.wait()

result: CommandResult = handle.result()

print(f"Command: {result.command}")
print(f"Status: {result.status}")
print(f"Duration: {result.duration:.2f}s")
print(f"Succeeded: {result.succeeded}")
print(f"Was cancelled: {result.was_cancelled}")
print(f"Details: {result.details}")

if result.error:
    print(f"Error: {result.error}")
```

## Use Cases

### Progress Logging

```python
async def fly_with_logging(drone, waypoints):
    for i, wp in enumerate(waypoints):
        print(f"Flying to waypoint {i+1}/{len(waypoints)}")
        
        handle = await drone.goto(coordinates=wp, wait=False)
        
        while handle.is_running:
            progress = handle.progress
            print(f"  Distance: {progress['distance']:.1f}m, "
                  f"Elapsed: {handle.elapsed_time:.1f}s")
            await asyncio.sleep(2)
        
        if handle.succeeded:
            print(f"  ✓ Arrived at {wp.name}")
        else:
            print(f"  ✗ Failed: {handle.error}")
            break
```

### Parallel Operations

```python
async def parallel_monitoring(drone):
    # Start long operation
    handle = await drone.goto(coordinates=far_target, wait=False)
    
    # Log telemetry while moving
    log_data = []
    while handle.is_running:
        log_data.append({
            "time": handle.elapsed_time,
            "position": drone.position,
            "battery": drone.battery.percentage,
            "distance": handle.progress.get("distance"),
        })
        await asyncio.sleep(0.5)
    
    print(f"Collected {len(log_data)} telemetry samples")
    return log_data
```

### Timeout with Custom Handling

```python
async def goto_with_fallback(drone, target, max_time=60):
    handle = await drone.goto(coordinates=target, timeout=max_time, wait=False)
    
    await handle.wait()
    
    if handle.timed_out:
        print(f"Timeout! {handle.progress['distance']:.1f}m away")
        # Try holding and retrying
        await drone.hold()
        await asyncio.sleep(5)
        return await goto_with_fallback(drone, target, max_time)
    
    return handle.succeeded
```

### Emergency Cancel

```python
async def mission_with_emergency_cancel(drone):
    waypoints = [...]
    current_handle = None
    
    async def emergency_check():
        while True:
            if drone.battery.is_critical:
                if current_handle and current_handle.is_running:
                    await current_handle.cancel()
                await drone.rtl()
                return
            await asyncio.sleep(1)
    
    # Start emergency monitoring in background
    emergency_task = asyncio.create_task(emergency_check())
    
    try:
        for wp in waypoints:
            current_handle = await drone.goto(coordinates=wp, wait=False)
            await current_handle  # Wait for completion or cancel
            
            if current_handle.was_cancelled:
                print("Mission cancelled due to emergency")
                break
    finally:
        emergency_task.cancel()
```

### Multiple Handles

```python
async def orbit_then_land(drone, center):
    # Start orbit
    orbit_handle = await drone.orbit(center=center, radius=30, revolutions=1, wait=False)
    
    # Monitor orbit
    while orbit_handle.is_running:
        print(f"Orbit progress: {orbit_handle.progress['progress_percent']:.0f}%")
        await asyncio.sleep(2)
    
    print("Orbit complete, landing...")
    
    # Start landing
    land_handle = await drone.land(wait=False)
    
    # Monitor landing
    while land_handle.is_running:
        print(f"Altitude: {land_handle.progress['current_altitude']:.1f}m")
        await asyncio.sleep(0.5)
    
    print("Landed!")
```

## Best Practices

### 1. Always Handle Errors

```python
try:
    handle = await drone.goto(coordinates=target, wait=False)
    await handle
except CommandCancelledError:
    # Handle cancellation
    pass
except TimeoutError:
    # Handle timeout
    await drone.hold()
```

### 2. Check Running Before Progress

```python
while handle.is_running:
    progress = handle.progress  # Safe - command is running
    print(progress)
    await asyncio.sleep(1)
```

### 3. Use Timeouts Appropriately

```python
# Set realistic timeouts based on distance/operation
distance = drone.position.distance_to(target)
timeout = distance / expected_speed * 1.5  # 50% buffer

handle = await drone.goto(coordinates=target, timeout=timeout, wait=False)
```

### 4. Clean Up on Errors

```python
handle = await drone.goto(coordinates=target, wait=False)

try:
    await handle
except Exception:
    # Ensure drone is in safe state
    await drone.hold()
    raise
```

### 5. Prefer Non-blocking for Long Operations

For operations that take significant time, non-blocking allows:
- Progress monitoring
- Battery/safety checks
- Telemetry logging
- User interruption

```python
# Good: can monitor and react
handle = await drone.goto(coordinates=far_target, wait=False)
while handle.is_running:
    if drone.battery.is_low:
        await handle.cancel()
        await drone.rtl()
        break
    await asyncio.sleep(1)

# Less flexible: blocks until complete
await drone.goto(coordinates=far_target)  # Can't check battery
```

