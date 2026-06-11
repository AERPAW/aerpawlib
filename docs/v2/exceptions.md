## Overview

Exception hierarchy for the v2 API. Each `AerpawlibError` carries `message`, `code`, `severity` (`warning`, `error`, `critical`), and optional `original_error`.

## When to use this

Import exception types when you handle failures in experiment scripts.

## Common workflow

```python
from aerpawlib.v2 import TakeoffError, NavigationError, AerpawlibError

try:
    await drone.takeoff(altitude=10)
except TakeoffError as e:
    print(e.code, e.message)
except AerpawlibError as e:
    print(e.severity, e)
```

## Key concepts

```
AerpawlibError
├── AerpawConnectionError (ConnectionTimeoutError, HeartbeatLostError, PortInUseError)
├── CommandError (ArmError, TakeoffError, NavigationError, …)
├── StateError (NotArmableError, NotConnectedError, UnexpectedDisarmError)
├── RunnerError (NoEntrypointError, InvalidStateError, …)
└── PlanError
```

`UnexpectedDisarmError` terminates the runner when the vehicle disarms mid-mission.

## See also

- `aerpawlib.v1.exceptions`: v1 hierarchy
- `aerpawlib.v2.vehicle`: command failures
- `aerpawlib.v2.runner`: configuration errors
