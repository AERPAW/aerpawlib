## Overview

Exception hierarchy for the v1 API. Catch `AerpawlibError` for broad handling or specific subclasses for targeted recovery.

## When to use this

Import exception types when you handle failures in experiment scripts or extend the library.

## Common workflow

```python
from aerpawlib.v1.exceptions import NavigationError, AerpawlibError

try:
    await vehicle.goto_coordinates(target)
except NavigationError as e:
    print(e.message)
except AerpawlibError as e:
    print(e)
```

## Key concepts

| Family | Examples |
|--------|----------|
| Connection | `ConnectionTimeoutError`, `HeartbeatLostError`, `PortInUseError` |
| Commands | `TakeoffError`, `NavigationError`, `ArmError`, `RTLError` |
| State | `NotConnectedError`, `NotArmableError` |
| Runner | `NoEntrypointError`, `InvalidStateError`, `StateMachineError` |
| Validation | `InvalidToleranceError`, `InvalidAltitudeError` |
| Platform | `AERPAWPlatformError`, `NotInAERPAWEnvironmentError` |

Wrap lower-level failures with `original_error` when re-raising.

## See also

- `aerpawlib.v2.exceptions`: v2 hierarchy with `code` and `severity`
- `aerpawlib.v1.vehicle`: command failures
- `aerpawlib.v1.runner`: configuration errors
