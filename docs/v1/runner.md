## Overview

Runners turn your Python class into an executable experiment. This module provides `BasicRunner`, `StateMachine`, and `ZmqStateMachine` plus the decorators that mark entry points and states.

## When to use this

Import from `aerpawlib.v1.runner` (or `aerpawlib.v1`) when you define experiment scripts launched by the `aerpawlib` CLI.

| Runner | Use when |
|--------|----------|
| `BasicRunner` | One linear `@entrypoint` flow |
| `StateMachine` | Named states with return-based transitions |
| `ZmqStateMachine` | Multi-vehicle coordination over ZMQ |

## Common workflow

```python
from aerpawlib.v1 import BasicRunner, Drone, entrypoint

class Patrol(BasicRunner):
    @entrypoint
    async def run(self, vehicle: Drone):
        await vehicle.takeoff(5)
        await vehicle.land()
```

```bash
aerpawlib --api-version v1 --script patrol.py --vehicle drone --conn udp:127.0.0.1:14550
```

## Key concepts

### Runner base

All runners subclass `Runner`. Optional hooks: `initialize_args` (extra CLI args), `cleanup` (shutdown).

### Decorators

Decorated methods must be `async`. State methods return the next state name (`str`) or `None` to finish.

| Decorator | Class | Description |
|-----------|-------|-------------|
| `@entrypoint` | `BasicRunner` | Single entry coroutine |
| `@state(name, first=False)` | `StateMachine` | Standard state |
| `@timed_state(name, duration, loop=False, first=False)` | `StateMachine` | State held for at least `duration` seconds |
| `@background` | `StateMachine` | Repeated background coroutine |
| `@at_init` | `StateMachine` | Runs once before arm |
| `@expose_zmq(name)` | `ZmqStateMachine` | Remote state transition target |
| `@expose_field_zmq(name)` | `ZmqStateMachine` | Queryable field via `query_field` |

### ZmqStateMachine setup

Initialize ZMQ before `run()` (normally via CLI `--zmq-identifier` and `--zmq-proxy-server`):

```python
self._initialize_zmq_bindings("vehicle-a", "127.0.0.1")
coords = await self.query_field("vehicle-b", "position")
await self.transition_runner("vehicle-b", "land")
```

### StateMachine example

```python
from aerpawlib.v1 import StateMachine, Vehicle, state, timed_state

class Patrol(StateMachine):
    @state(name="start", first=True)
    async def start(self, vehicle: Vehicle):
        await vehicle.takeoff(5)
        return "hold"

    @timed_state(name="hold", duration=10)
    async def hold(self, vehicle: Vehicle):
        return "land"

    @state(name="land")
    async def land(self, vehicle: Vehicle):
        await vehicle.land()
```

## Errors

| Exception | Cause |
|-----------|-------|
| `NoEntrypointError` | `BasicRunner` missing `@entrypoint` |
| `NoInitialStateError` | No state with `first=True` |
| `MultipleInitialStatesError` | More than one `first=True` state |
| `InvalidStateError` | Returned state name not defined |
| `StateMachineError` | ZMQ not initialized or other runtime config issue |

## See also

- `aerpawlib.v1.vehicle`: vehicle passed to runner methods
- `aerpawlib.cli`: `--script`, ZMQ flags
- `aerpawlib.v2.runner`: v2 runner API
