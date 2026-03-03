# v1 to v2 Migration Guide

This guide helps you migrate scripts from aerpawlib v1 to v2.

## Significant Changes

| Area       | v1                                     | v2                                           |
|------------|----------------------------------------|----------------------------------------------|
| Runners    | `inspect.getmembers` + function attrs  | Config dataclass or decorators               |
| Safety     | `SafetyCheckerClient`, `SafetyMonitor` | `vehicle.safety` + `can_takeoff`, `can_goto` |
| Types      | `aerpawlib.v1.util`                    | `aerpawlib.v2.types`                         |
| Plan files | `aerpawlib.v1.util.read_from_plan`     | `aerpawlib.v2.plan.read_from_plan`           |


## Runners

v1 (function attributes):
```python
class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        ...
```

v2 (config dataclass or decorators):
```python
# Decorator style (backward compatible)
class MyMission(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        ...

# Explicit config style
class MyMission(BasicRunner):
    config = BasicRunnerConfig(entrypoint="run")
    async def run(self, drone: Drone):
        ...
```

## Safety and Command Validation

v1: Use `SafetyCheckerClient` explicitly; optional `SafetyMonitor` for warnings.

v2: Use `can_takeoff`, `can_goto`, `can_land` before commands. Pass a safety client to `connect(safety=...)`; when running via CLI, aerpawlib builds and passes it from `--safety-checker-port` (in AERPAW defaults to 14580; outside AERPAW optional with passthrough on failure):

```python
from aerpawlib.v2.safety import SafetyCheckerClient

client = SafetyCheckerClient("127.0.0.1", 14580)
drone = await Drone.connect(conn, safety=client)
ok, msg = await drone.can_takeoff(10)
if not ok:
    return
await drone.takeoff(altitude=10)
```

## Types and Plan Files

| v1                                                    | v2                                                     |
|-------------------------------------------------------|--------------------------------------------------------|
| `from aerpawlib.v1.util import Coordinate, VectorNED` | `from aerpawlib.v2.types import Coordinate, VectorNED` |
| `read_from_plan`, `read_from_plan_complete`           | `aerpawlib.v2.plan` (same API)                         |
