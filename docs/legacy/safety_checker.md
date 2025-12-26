# Safety Checker Guide (Legacy)

The legacy API includes a safety checker system for geofence validation using ZMQ communication.

> **Note**: For comprehensive safety features including pre-flight checks, battery failsafe, and parameter validation, consider upgrading to the [v2 API](../v2/safety.md).

## Overview

The safety checker system consists of:

| Component | Description |
|-----------|-------------|
| `SafetyCheckerServer` | Runs geofence validation, receives requests via ZMQ |
| `SafetyCheckerClient` | Sends validation requests to the server |

## Quick Start

### 1. Create a Geofence Configuration

```yaml
# geofence_config.yaml
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

### 2. Start the Server

```python
from aerpawlib.legacy.safetyChecker import SafetyCheckerServer

server = SafetyCheckerServer("geofence_config.yaml", server_port=14580)
server.start_server()  # Blocks
```

### 3. Connect from Your Script

```python
from aerpawlib.legacy.safetyChecker import SafetyCheckerClient

client = SafetyCheckerClient("127.0.0.1", 14580)

# Check server status
if client.checkServerStatus():
    print("Server is running")

# Validate waypoint before flying
result = client.validateWaypoint(current_pos, target_pos)
if result:
    print("Waypoint is valid")
else:
    print("Waypoint outside geofence!")
```

---

## SafetyCheckerServer

### Initialization

```python
from aerpawlib.legacy.safetyChecker import SafetyCheckerServer

# Create server with YAML config
server = SafetyCheckerServer(
    vehicle_config="geofence_config.yaml",
    server_port=14580
)
```

### Starting the Server

```python
# Blocking - runs until interrupted
server.start_server()

# Or specify port at runtime
server.start_server(port=14581)
```

### Configuration Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `vehicle_type` | `str` | "copter" or "rover" |
| `max_speed` | `float` | Maximum allowed speed (m/s) |
| `min_speed` | `float` | Minimum allowed speed (m/s) |
| `max_alt` | `float` | Maximum altitude for copters (m) |
| `min_alt` | `float` | Minimum altitude for copters (m) |
| `include_geofences` | `list` | KML files defining allowed areas |
| `exclude_geofences` | `list` | KML files defining no-go zones |

---

## SafetyCheckerClient

### Initialization

```python
from aerpawlib.legacy.safetyChecker import SafetyCheckerClient

client = SafetyCheckerClient(
    server_address="127.0.0.1",
    server_port=14580
)
```

### Methods

#### `checkServerStatus() -> bool`

Check if the server is running and responsive.

```python
if client.checkServerStatus():
    print("Server is running")
else:
    print("Server not responding")
```

#### `validateWaypoint(current: Coordinate, target: Coordinate) -> bool`

Validate that a waypoint is within geofences.

```python
from aerpawlib.legacy import Coordinate

current = Coordinate(35.7275, -78.6960, 10)
target = Coordinate(35.7280, -78.6955, 15)

if client.validateWaypoint(current, target):
    await drone.goto_coordinates(target)
else:
    print("Target is outside geofence!")
```

#### `validateSpeed(speed: float) -> bool`

Validate that a speed is within limits.

```python
if client.validateSpeed(15.0):
    await drone.set_groundspeed(15.0)
else:
    print("Speed exceeds limit!")
```

#### `validateTakeoff(altitude: float, lat: float, lon: float) -> bool`

Validate a takeoff command.

```python
if client.validateTakeoff(10, drone.position.lat, drone.position.lon):
    await drone.takeoff(10)
else:
    print("Cannot take off at this location!")
```

---

## Geofence Files

### KML Format

Create geofence polygons using KML files:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Flight Area</name>
    <Placemark>
      <name>Allowed Area</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -78.70,35.70,0
              -78.60,35.70,0
              -78.60,35.80,0
              -78.70,35.80,0
              -78.70,35.70,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
```

### Creating KML Files

You can create KML files using:
- Google Earth Pro
- QGIS
- Online KML generators
- Programmatically with Python

### Multiple Geofences

You can have multiple geofences:

```yaml
include_geofences:
  - area1.kml
  - area2.kml
  - area3.kml
exclude_geofences:
  - no_fly_zone1.kml
  - no_fly_zone2.kml
```

The drone must be inside at least one include geofence and outside all exclude geofences.

---

## Example: Full Integration

```python
from aerpawlib.legacy import Drone, Coordinate, BasicRunner, entrypoint
from aerpawlib.legacy.safetyChecker import SafetyCheckerClient

class SafeMission(BasicRunner):
    def __init__(self):
        self.checker = SafetyCheckerClient("127.0.0.1", 14580)
    
    @entrypoint
    async def run(self, drone: Drone):
        # Verify safety checker is running
        if not self.checker.checkServerStatus():
            print("ERROR: Safety checker not running!")
            return
        
        # Validate takeoff
        pos = drone.position
        if not self.checker.validateTakeoff(10, pos.lat, pos.lon):
            print("Cannot take off at this location")
            return
        
        await drone.takeoff(10)
        
        # Define waypoints
        waypoints = [
            Coordinate(35.7275, -78.6960, 10),
            Coordinate(35.7280, -78.6955, 15),
            Coordinate(35.7270, -78.6950, 10),
        ]
        
        # Validate each waypoint before flying
        for wp in waypoints:
            if self.checker.validateWaypoint(drone.position, wp):
                await drone.goto_coordinates(wp)
            else:
                print(f"Waypoint {wp} is outside geofence, skipping!")
        
        await drone.land()
```

---

## Troubleshooting

### Server Not Starting

```python
# Check that config file exists and is valid
import yaml
with open("geofence_config.yaml") as f:
    config = yaml.safe_load(f)
    print(config)
```

### Connection Failed

```python
import zmq

try:
    client = SafetyCheckerClient("127.0.0.1", 14580)
    client.checkServerStatus()
except zmq.ZMQError as e:
    print(f"Connection failed: {e}")
```

### Geofence Not Loading

Check that:
1. KML files exist in the same directory as the config
2. KML files are valid XML
3. Coordinates are in the correct format (lon,lat,alt)

---

## Upgrading to v2

The v2 API offers a more comprehensive safety system:

```python
# v2 with full safety features
from aerpawlib.v2 import Drone, SafetyLimits, SafetyCheckerClient

async with SafetyCheckerClient("localhost", 14580) as checker:
    drone = Drone(
        "udp://:14540",
        safety_limits=SafetyLimits.restrictive(),
        safety_checker=checker
    )
    # Pre-flight checks, battery failsafe, parameter validation all included
```

See the [v2 Safety Guide](../v2/safety.md) for details.

