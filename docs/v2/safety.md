# Safety Features Guide

The v2 API includes comprehensive safety features designed to help researchers avoid common mistakes that could damage drones or cause crashes.

## Consolidated Safety Module

All safety features are now consolidated in `safety.py`, providing a unified interface for:

| Component | Purpose |
|-----------|---------|
| `SafetyLimits` | Configurable safety parameters for client-side validation |
| `SafetyConfig` | YAML-based configuration for server |
| `SafetyMonitor` | Background runtime monitoring for battery/speed |
| `SafetyCheckerClient` | ZMQ client for external geofence validation |
| `SafetyCheckerServer` | ZMQ server for geofence enforcement |
| Validation functions | Parameter validation (`validate_coordinate`, etc.) |
| Exception classes | `SafetyError`, `GeofenceViolationError`, etc. |

### Import Options

All safety features can be imported from multiple locations:

```python
# From the safety module directly
from aerpawlib.v2.safety import SafetyLimits, SafetyCheckerClient, SafetyError

# From the main package
from aerpawlib.v2 import SafetyLimits, SafetyCheckerClient, SafetyError

# Exceptions can also be imported from exceptions.py
from aerpawlib.v2.exceptions import SafetyError, GeofenceViolationError
```

### Two-Layer Architecture

The safety system operates in two complementary layers:

| Layer | Purpose | When to Use |
|-------|---------|-------------|
| **Client-side** | Parameter validation, pre-flight checks, battery failsafe | Always (automatic) |
| **Server-side** | Geofence enforcement, waypoint validation | Production flights |

- **Client-side only** (default): Good for testing and simple missions. Uses `SafetyLimits`.
- **Both layers**: Recommended for production. Run `SafetyCheckerServer` and connect via `SafetyCheckerClient`.

## Overview

| Feature | Description | Default |
|---------|-------------|---------|
| SafetyLimits | Configurable safety parameters | Enabled |
| Pre-flight Checks | Validate before arming | Enabled |
| Parameter Validation | Validate command inputs | Enabled |
| Speed Limits | Max speed enforcement | 15 m/s |
| Battery Failsafe | Auto-RTL on low battery | Enabled |
| Safety Monitor | Background safety monitoring | Enabled |
| Geofence Validation | Server-side waypoint checks | Requires SafetyCheckerServer |

## Quick Start

```python
from aerpawlib.v2 import Drone, SafetyLimits

# Use default safety limits (recommended for beginners)
drone = Drone("udp://:14540")

# Or use restrictive preset for extra safety
drone = Drone("udp://:14540", safety_limits=SafetyLimits.restrictive())

# Run pre-flight checks before arming
result = await drone.preflight_check()
if not result:
    print(f"Pre-flight failed: {result.failed_checks}")
    print(result.summary())
else:
    await drone.arm()
```

---

## Using SafetyCheckerServer for Geofence Validation

For production flights, use the safety checker server to enforce geofences.

### 1. Create a Safety Config YAML

```yaml
# mission_config.yaml
vehicle_type: copter
max_speed: 15
min_speed: 0.5
max_alt: 120
min_alt: 5
include_geofences:
  - flight_area.kml
exclude_geofences:
  - no_fly_zone.kml
```

### 2. Start the Safety Checker Server

```python
# In a separate process/terminal
from aerpawlib.v2 import SafetyCheckerServer, SafetyConfig

# Option 1: Pass YAML path
server = SafetyCheckerServer("mission_config.yaml", port=14580)
await server.serve()

# Option 2: Pass SafetyConfig object
config = SafetyConfig.from_yaml("mission_config.yaml")
server = SafetyCheckerServer(config, port=14580)
await server.serve()
```

Or from command line:
```bash
python -m aerpawlib.v2.safety_checker --vehicle_config mission_config.yaml --port 14580
```

### 3. Connect Your Drone to the Server

```python
from aerpawlib.v2 import Drone, SafetyLimits, SafetyCheckerClient

async def main():
    # Connect to safety checker server
    async with SafetyCheckerClient("localhost", 14580) as checker:
        # Create drone with safety checker
        drone = Drone(
            "udp://:14540",
            safety_limits=SafetyLimits.restrictive(),
            safety_checker=checker
        )
        
        await drone.connect()
        await drone.arm()
        await drone.takeoff(altitude=10)  # Validated by server
        
        # This will raise GeofenceViolationError if outside geofence
        await drone.goto(latitude=35.7, longitude=-78.6)
        
        await drone.land()
```

### 4. Unified Configuration

Use the same YAML for both server and client:

```python
from aerpawlib.v2 import SafetyConfig, SafetyLimits, SafetyCheckerServer, SafetyCheckerClient

# Load YAML config
config = SafetyConfig.from_yaml("mission_config.yaml")

# Use for server
server = SafetyCheckerServer(config, port=14580)

# Use for client limits (inherits max_speed from config)
limits = SafetyLimits.from_safety_config(config)

async with SafetyCheckerClient("localhost", 14580) as checker:
    drone = Drone("udp://:14540", safety_limits=limits, safety_checker=checker)
    # ...
```

---

## SafetyLimits Configuration

`SafetyLimits` is a dataclass that configures all client-side safety parameters.

### Default Values

```python
SafetyLimits(
    # Speed limits
    max_speed=15.0,           # m/s horizontal
    max_vertical_speed=5.0,   # m/s vertical
    
    # Battery limits
    min_battery_percent=20.0,      # warning threshold
    critical_battery_percent=10.0, # RTL threshold
    
    # GPS requirements
    require_gps_fix=True,
    min_satellites=6,
    
    # Feature toggles
    enable_speed_limits=True,
    enable_battery_failsafe=True,
    enable_parameter_validation=True,
    enable_preflight_checks=True,
    auto_clamp_values=True,
)
```

### Presets

```python
# For beginners - very conservative limits
drone = Drone("udp://:14540", safety_limits=SafetyLimits.restrictive())
# max_speed=5.0, max_vertical_speed=2.0, min_battery=30%, min_satellites=8

# For advanced users - relaxed limits
drone = Drone("udp://:14540", safety_limits=SafetyLimits.permissive())
# max_speed=30.0, no battery failsafe, no preflight checks

# Disable all safety (experts only!)
drone = Drone("udp://:14540", safety_limits=SafetyLimits.disabled())
```

### Custom Configuration

```python
from aerpawlib.v2 import Drone, SafetyLimits

# Custom limits for your use case
limits = SafetyLimits(
    max_speed=10.0,               # 10 m/s max
    min_battery_percent=25.0,     # Warn at 25%
    critical_battery_percent=15.0, # RTL at 15%
    min_satellites=8,              # Require 8 sats
    auto_clamp_values=True,        # Clamp instead of reject
)

drone = Drone("udp://:14540", safety_limits=limits)
```

---

## SafetyConfig (Server Configuration)

`SafetyConfig` is used by `SafetyCheckerServer` for geofence validation.

### YAML Format

```yaml
# config.yaml
vehicle_type: copter      # or "rover"
max_speed: 15             # m/s
min_speed: 0.5            # m/s
max_alt: 120              # meters (copter only)
min_alt: 5                # meters (copter only)
include_geofences:        # allowed flight areas (KML files)
  - flight_area.kml
exclude_geofences:        # no-go zones (KML files)
  - no_fly_zone.kml
```

### Loading Configuration

```python
from aerpawlib.v2 import SafetyConfig

# Load from YAML
config = SafetyConfig.from_yaml("mission_config.yaml")

# Access properties
print(f"Vehicle type: {config.vehicle_type}")
print(f"Max speed: {config.max_speed}")
print(f"Geofences: {len(config.include_geofences)}")
```

---

## Pre-flight Checks

Pre-flight checks run automatically before arming (unless skipped) and validate:

- GPS fix quality and satellite count
- Battery level
- Safety configuration validity
- Connection health

### Running Manually

```python
result = await drone.preflight_check()

if result:
    print("All checks passed!")
else:
    print(f"Failed checks: {result.failed_checks}")
    for name, check in result.checks.items():
        status = "✓" if check.passed else "✗"
        print(f"  {status} {name}: {check.message}")
    
    # Show warnings
    for warning in result.warnings:
        print(f"  ⚠ {warning}")
```

### Pre-flight Check Details

```python
# Get a detailed summary
print(result.summary())

# Output:
# Pre-flight Check Results:
# ========================================
#   ✓ PASS: config
#   ✓ PASS: gps
#   ✗ FAIL: battery - Battery too low: 15.0%
# ========================================
# Warnings:
#   ⚠ Battery at 45.0% - consider charging before long flights
# ========================================
# Result: FAILED
```

### Skipping Pre-flight

```python
# Skip pre-flight (not recommended)
await drone.arm(skip_preflight=True)

# Force arm even if checks fail (dangerous!)
await drone.arm(force=True)
```

---

## Parameter Validation

When `enable_parameter_validation=True`, all command parameters are validated.

### Validated Parameters

| Command | Parameters Validated |
|---------|---------------------|
| `goto()` | coordinates, altitude, tolerance, timeout, speed |
| `takeoff()` | altitude |
| `set_velocity()` | velocity vector |
| `orbit()` | center, radius, speed |

### What's Validated

- **Coordinates**: Valid lat/lon ranges, not NaN/Inf
- **Altitudes**: Not NaN/Inf, reasonable values
- **Speeds**: Positive, within limits
- **Tolerances**: Positive, minimum 0.1m
- **Timeouts**: Positive, max 1 hour

### Auto-Clamping

When `auto_clamp_values=True`, invalid values are clamped instead of rejected:

```python
# With auto_clamp_values=True (default)
await drone.goto(coordinates=target, speed=100)  # Clamped to 15 m/s

# With auto_clamp_values=False
await drone.goto(coordinates=target, speed=100)  # Raises ParameterValidationError
```

---

## Battery Failsafe

When `enable_battery_failsafe=True`, the safety monitor:

1. Warns when battery drops below `min_battery_percent`
2. Automatically triggers RTL when battery drops below `critical_battery_percent`

### Configuration

```python
limits = SafetyLimits(
    min_battery_percent=20.0,      # Warn at 20%
    critical_battery_percent=10.0, # RTL at 10%
    enable_battery_failsafe=True,
)
```

### Customizing Response

Register callbacks for battery events:

```python
from aerpawlib.v2 import SafetyViolationType

# Register callback with safety monitor
drone._safety_monitor.on_violation(
    SafetyViolationType.BATTERY_CRITICAL,
    my_custom_handler
)

drone._safety_monitor.on_violation(
    SafetyViolationType.BATTERY_LOW,
    lambda v, msg: print(f"Warning: {msg}")
)
```

---

## Speed Limits

Speed limits are enforced in two ways:

1. **Parameter validation**: Rejects or clamps speed parameters in commands
2. **Safety monitor**: Warns if actual speed exceeds limits

### Configuration

```python
limits = SafetyLimits(
    max_speed=15.0,           # m/s horizontal
    max_vertical_speed=5.0,   # m/s vertical
    enable_speed_limits=True,
)
```

### Clamping Functions

```python
from aerpawlib.v2 import clamp_speed, clamp_velocity, VectorNED, SafetyLimits

limits = SafetyLimits(max_speed=15.0)

# Clamp a speed value
speed = clamp_speed(100, limits)  # Returns 15.0

# Clamp a velocity vector
velocity = VectorNED(50, 0, 0)  # 50 m/s north
clamped = clamp_velocity(velocity, limits)  # Returns VectorNED(15, 0, 0)
```

---

## Safety Monitor

The `SafetyMonitor` runs in the background during flight and:

- Monitors speed limits
- Monitors battery levels
- Triggers warnings and failsafes
- Logs safety events

### How It Works

1. Started automatically when you call `drone.connect()`
2. Runs checks every 0.5 seconds
3. Triggers callbacks on violations
4. Auto-RTL on critical battery (if enabled)

### Registering Callbacks

```python
from aerpawlib.v2 import SafetyViolationType

# Register a callback for a specific violation type
drone._safety_monitor.on_violation(
    SafetyViolationType.SPEED_TOO_HIGH,
    lambda violation, message: print(f"Speed warning: {message}")
)

drone._safety_monitor.on_violation(
    SafetyViolationType.BATTERY_CRITICAL,
    my_emergency_handler
)
```

### Violation Types

```python
from aerpawlib.v2 import SafetyViolationType

# Available violation types:
SafetyViolationType.SPEED_TOO_HIGH
SafetyViolationType.VERTICAL_SPEED_TOO_HIGH
SafetyViolationType.BATTERY_LOW
SafetyViolationType.BATTERY_CRITICAL
SafetyViolationType.GPS_POOR
SafetyViolationType.NO_GPS_FIX
SafetyViolationType.INVALID_COORDINATE
SafetyViolationType.INVALID_ALTITUDE
SafetyViolationType.INVALID_SPEED
SafetyViolationType.INVALID_PARAMETER
SafetyViolationType.PREFLIGHT_FAILED
SafetyViolationType.GEOFENCE_VIOLATION
SafetyViolationType.NO_GO_ZONE_VIOLATION
SafetyViolationType.PATH_LEAVES_GEOFENCE
SafetyViolationType.PATH_ENTERS_NO_GO_ZONE
SafetyViolationType.ALTITUDE_OUT_OF_BOUNDS
```

---

## Validation Functions

Use these functions for manual parameter validation:

```python
from aerpawlib.v2 import (
    validate_coordinate,
    validate_altitude,
    validate_speed,
    validate_velocity,
    validate_timeout,
    validate_tolerance,
    SafetyLimits,
)

limits = SafetyLimits()

# Validate a coordinate
result = validate_coordinate(my_coord)
if not result:
    print(f"Invalid: {result.message}")

# Validate speed against limits
result = validate_speed(speed, limits)
if not result:
    print(f"Speed violation: {result.message}")
    print(f"Value: {result.value}, Limit: {result.limit}")

# Validate altitude
result = validate_altitude(altitude)
if not result:
    print(f"Invalid altitude: {result.message}")
```

---

## Exception Handling

All safety exceptions inherit from `SafetyError` (which inherits from `AerpawlibError`):

```
AerpawlibError
└── SafetyError
    ├── GeofenceViolationError
    ├── SpeedLimitExceededError
    ├── ParameterValidationError
    └── (more...)

AerpawlibError
└── PreflightError
    └── PreflightCheckError
```

### Exception Classes

| Exception | When Raised |
|-----------|-------------|
| `SafetyError` | Base class for safety errors |
| `GeofenceViolationError` | Command would violate geofence |
| `SpeedLimitExceededError` | Speed exceeds limits |
| `ParameterValidationError` | Invalid command parameter |
| `PreflightCheckError` | Pre-flight checks failed |

### Usage Example

```python
from aerpawlib.v2 import (
    PreflightCheckError,
    ParameterValidationError,
    SpeedLimitExceededError,
    GeofenceViolationError,
    SafetyError,
)

try:
    await drone.arm()
except PreflightCheckError as e:
    print(f"Pre-flight failed: {e.result.failed_checks}")
    print(e.result.summary())

try:
    await drone.goto(coordinates=target)
except GeofenceViolationError as e:
    print(f"Geofence violation: {e.message}")
    print(f"Current: {e.current_position}")
    print(f"Target: {e.target_position}")
except ParameterValidationError as e:
    print(f"Invalid {e.parameter}: {e.message}")
except SpeedLimitExceededError as e:
    print(f"Speed {e.value} exceeds limit {e.limit}")
except SafetyError as e:
    # Catch-all for any safety error
    print(f"Safety error: {e.message}")
```

---

## Examples

### Safe Mission with Pre-flight

```python
from aerpawlib.v2 import Drone, Coordinate, SafetyLimits, BasicRunner, entrypoint
from aerpawlib.v2 import PreflightCheckError

class SafeMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.connect()
        
        # Pre-flight checks run automatically in arm()
        try:
            await drone.arm()
        except PreflightCheckError as e:
            print(f"Cannot fly: {e.result.summary()}")
            return
        
        await drone.takeoff(altitude=10)
        await drone.goto(coordinates=Coordinate(35.7, -78.6, 10))
        await drone.land()
```

### Custom Safety Configuration

```python
from aerpawlib.v2 import Drone, SafetyLimits, BasicRunner, entrypoint

class ConservativeMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        # Extra conservative limits
        limits = SafetyLimits(
            max_speed=5.0,
            min_battery_percent=30.0,
            critical_battery_percent=20.0,
            min_satellites=8,
        )
        
        drone = Drone("udp://:14540", safety_limits=limits)
        await drone.connect()
        await drone.arm()
        # ... mission ...
```

### Production Flight with Geofence Server

```python
from aerpawlib.v2 import (
    Drone, SafetyLimits, SafetyCheckerClient, SafetyConfig,
    BasicRunner, entrypoint, GeofenceViolationError
)

class ProductionMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        # Load config for client-side limits
        config = SafetyConfig.from_yaml("mission_config.yaml")
        limits = SafetyLimits.from_safety_config(config)
        
        # Connect to safety checker server
        async with SafetyCheckerClient("localhost", 14580) as checker:
            drone = Drone(
                "udp://:14540",
                safety_limits=limits,
                safety_checker=checker
            )
            
            await drone.connect()
            await drone.arm()
            await drone.takeoff(altitude=10)
            
            try:
                await drone.goto(latitude=35.7, longitude=-78.6)
            except GeofenceViolationError as e:
                print(f"Cannot navigate: {e.message}")
                await drone.rtl()
            
            await drone.land()
```

### Handling Validation Errors

```python
from aerpawlib.v2 import (
    Drone, Coordinate, ParameterValidationError, SafetyLimits
)

# Disable auto-clamping to get validation errors
limits = SafetyLimits(auto_clamp_values=False)
drone = Drone("udp://:14540", safety_limits=limits)

try:
    # This will fail - speed is too high
    await drone.goto(
        coordinates=Coordinate(35.7, -78.6, 10),
        speed=100  # Exceeds max_speed
    )
except ParameterValidationError as e:
    print(f"Invalid {e.parameter}: {e.message}")
    print(f"Value: {e.value}")
```

---

## Disabling Safety Features

**Warning**: Only disable safety features if you know what you're doing!

```python
# Disable specific features
limits = SafetyLimits(
    enable_battery_failsafe=False,  # No auto-RTL on low battery
    enable_preflight_checks=False,  # No pre-flight validation
    enable_parameter_validation=False,  # No parameter validation
    enable_speed_limits=False,  # No speed limit enforcement
)

# Or use the disabled preset
limits = SafetyLimits.disabled()
```

---

## Best Practices

1. **Use defaults for learning** - The default `SafetyLimits` are good for most cases
2. **Run pre-flight checks** - Don't skip them unless you have a good reason
3. **Keep battery failsafe on** - It can save your drone
4. **Use auto-clamping** - Better to clamp than crash on invalid values
5. **Monitor warnings** - Safety warnings indicate potential problems
6. **Test in simulation first** - Verify your safety settings before real flights
7. **Use SafetyCheckerServer for production** - Geofence validation prevents flyaways
8. **Handle exceptions gracefully** - Always have a fallback (RTL) plan
