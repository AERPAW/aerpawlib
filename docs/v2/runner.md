## Overview

Runners turn your Python class into an executable experiment. This module provides `BasicRunner`, `StateMachine`, and `ZmqStateMachine` plus decorators and optional config dataclasses.

## When to use this

Import from `aerpawlib.v2.runner` (or `aerpawlib.v2`) when you define experiment scripts launched by the `aerpawlib` CLI.

| Runner | Use when |
|--------|----------|
| `BasicRunner` | One linear `@entrypoint` flow |
| `StateMachine` | Named states with return-based transitions |
| `ZmqStateMachine` | Multi-vehicle coordination over ZMQ |

## Common workflow

```python
from aerpawlib.v2 import BasicRunner, Drone, entrypoint

class Patrol(BasicRunner):
    @entrypoint
    async def run(self, drone: Drone):
        await drone.takeoff(altitude=5)
        await drone.land()
```

```bash
aerpawlib --api-version v2 --script patrol.py --vehicle drone --conn udpin://127.0.0.1:14550
```

## Key concepts

### Decorators (default)

| Decorator | Class | Description |
|-----------|-------|-------------|
| `@entrypoint` | `BasicRunner` | Single entry coroutine |
| `@state(name, first=False)` | `StateMachine` | Standard state |
| `@timed_state(name, duration, loop=False, first=False)` | `StateMachine` | State held for at least `duration` seconds |
| `@background` | `StateMachine` | Concurrent coroutine restarted on exception |
| `@at_init` | `StateMachine` | Runs once before arm and first state |
| `@expose_zmq(name)` | `ZmqStateMachine` | Remote state transition target |
| `@expose_field_zmq(name)` | `ZmqStateMachine` | Queryable field via `query_field` |

### Config dataclasses (optional)

Set `config = BasicRunnerConfig(entrypoint="run")`, `StateMachineConfig`, or `ZmqStateMachineConfig` on the class instead of relying solely on decorators.

### ZMQ

1. Start `aerpawlib-run-proxy`
2. Launch runners with `--zmq-identifier` and `--zmq-proxy-server`

```python
await self.transition_runner("other-vehicle", "land")
alt = await self.query_field("other-vehicle", "altitude")
```

### StateMachine example

```python
from aerpawlib.v2 import StateMachine, Drone, state, timed_state, at_init

class Patrol(StateMachine):
    @at_init
    async def setup(self, drone: Drone):
        print(drone.home_coords)

    @state(name="start", first=True)
    async def start(self, drone: Drone):
        await drone.takeoff(altitude=5)
        return "hold"

    @timed_state(name="hold", duration=10)
    async def hold(self, drone: Drone):
        return "land"

    @state(name="land")
    async def land(self, drone: Drone):
        await drone.land()
```

## Errors

Misconfigured runners raise `RunnerError` subclasses: `NoEntrypointError`, `NoInitialStateError`, `MultipleInitialStatesError`, `InvalidStateError`, `InvalidStateNameError`. See `aerpawlib.v2.exceptions`.

## See also

- `aerpawlib.v2.vehicle`: vehicle passed to runner methods
- `aerpawlib.cli`: `--script`, ZMQ flags
- `aerpawlib.v1.runner`: v1 runner API
