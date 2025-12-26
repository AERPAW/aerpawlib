# aerpawlib Documentation

Welcome to the aerpawlib documentation. aerpawlib is a Python library for autonomous vehicle control, providing a clean async API for drones and rovers.

## API Versions

aerpawlib offers three API versions to accommodate different needs:

| Version | Backend | Status | Recommended For |
|---------|---------|--------|-----------------|
| [**v2**](v2/README.md) | MAVSDK | ✅ **Recommended** | New projects |
| [v1](v1/README.md) | MAVSDK | ✅ Stable | Legacy code migration |
| [legacy](legacy/README.md) | DroneKit | ⚠️ Deprecated | Reference only |

## Quick Comparison

| Feature | Legacy | v1 | v2 |
|---------|--------|-----|-----|
| Backend | DroneKit | MAVSDK | MAVSDK |
| Python | 3.7+ | 3.8+ | 3.8+ |
| Async | Basic | Basic | Native |
| Context managers | ❌ | ❌ | ✅ |
| CommandHandle | ❌ | ❌ | ✅ |
| Progress tracking | ❌ | ❌ | ✅ |
| Structured exceptions | ❌ | ❌ | ✅ |
| Event callbacks | Limited | Limited | ✅ |
| Flight recording | ❌ | ❌ | ✅ |
| Property-based state | ❌ | ❌ | ✅ |
| Pre-flight checks | ❌ | ❌ | ✅ |
| Battery failsafe | ❌ | ❌ | ✅ |
| Parameter validation | ❌ | ❌ | ✅ |
| Geofence validation | ✅ | ✅ | ✅ |

## Installation

```bash
pip install aerpawlib

# For v1/v2 (MAVSDK backend)
pip install mavsdk

# For safety checker (all versions)
pip install pyzmq pyyaml

# For legacy (DroneKit backend)
pip install dronekit pymavlink
```

## Quick Start

### v2 API (Recommended)

```python
from aerpawlib.v2 import Drone, Coordinate, BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.connect()
        await drone.arm()  # Pre-flight checks run automatically
        await drone.takeoff(altitude=10)
        await drone.goto(coordinates=Coordinate(35.7, -78.6, 10))
        await drone.land()
```

### v1 API

```python
from aerpawlib.v1 import Drone, Coordinate, BasicRunner, entrypoint

class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(10)
        await drone.goto_coordinates(Coordinate(35.7, -78.6, 10))
        await drone.land()
```

## Documentation Index

### v2 API
- [README](v2/README.md) - Full API reference
- [Safety Features](v2/safety.md) - Pre-flight checks, battery failsafe, geofences
- [CommandHandle Guide](v2/command_handle.md) - Non-blocking operations
- [Migration Guide](v2/migration.md) - Migrating from legacy/v1

### v1 API
- [README](v1/README.md) - API reference, runners, utility types
- [Safety Checker](v1/safety_checker.md) - Geofence validation guide

### Legacy API
- [README](legacy/README.md) - API reference, runners, utility types
- [Safety Checker](legacy/safety_checker.md) - Geofence validation guide

## Safety Features Comparison

| Feature | Legacy | v1 | v2 |
|---------|--------|-----|-----|
| Geofence server | ✅ | ✅ | ✅ |
| Pre-flight checks | ❌ | ❌ | ✅ |
| Battery failsafe | ❌ | ❌ | ✅ |
| Speed limits | ❌ | ❌ | ✅ |
| Parameter validation | ❌ | ❌ | ✅ |
| Safety monitor | ❌ | ❌ | ✅ |
| Auto-clamp values | ❌ | ❌ | ✅ |
| Configurable limits | ❌ | ❌ | ✅ |

For comprehensive safety features, use the [v2 API](v2/README.md). See the [Safety Features Guide](v2/safety.md) for details.

## Examples

See the [`examples/`](../examples/) directory for working examples:

- [`examples/v2/`](../examples/v2/) - v2 API examples
- [`examples/v1/`](../examples/v1/) - v1 API examples
- [`examples/legacy/`](../examples/legacy/) - Legacy API examples

## Connection Strings

All versions use similar connection strings:

```python
# SITL / UDP
"udp://:14540"
"udp://127.0.0.1:14540"

# Serial
"serial:///dev/ttyUSB0:57600"
"serial:///dev/ttyACM0:115200"

# TCP
"tcp://192.168.1.100:5760"
```

## Vehicle Types

| Type | Description | Available In |
|------|-------------|--------------|
| `Drone` | Multicopter (takeoff, land, 3D movement) | All versions |
| `Rover` | Ground vehicle (2D movement) | All versions |
| `DummyVehicle` | For scripts without vehicles | All versions |

## Support

- Check the relevant API documentation
- Review the examples
- Open an issue on GitHub
