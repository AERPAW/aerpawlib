## Overview

Runner API for v1 experiments.

This module provides runner implementations and decorators used to build v1
missions with either a single-entry flow (`BasicRunner`) or a state-machine
flow (`StateMachine` / `ZmqStateMachine`).

High-level overview
-------------------
- `Runner`
  - Abstract base class. Subclasses should implement `run(self, vehicle)`
    with the execution model they want (basic single-entry scripts, state
    machines, etc.). Optional hooks: `initialize_args` and `cleanup`.

- `BasicRunner`
  - Discovers a single `@entrypoint` method on the instance and executes
    it. Used for simple scripts where the user controls flow itself. If more
    than one entrypoint is found, a `StateMachineError` is raised; if no
    entrypoint is found, `NoEntrypointError` is raised.

- `StateMachine`
  - Builds a map of states from methods decorated with `@state` or
    `@timed_state` (see `aerpawlib.v1.runner.decorators`). One state
    must be marked as the initial state (`first=True`) or a
    `NoInitialStateError` is raised; multiple "first" states raise
    `MultipleInitialStatesError`.
  - Execution model: the current state's wrapped function is awaited and the
    returned string is used as the next state's name. Timed states are
    supported via an internal `_State` wrapper; background tasks and
    initialization tasks are supported and discovered by attributes set by
    decorators (`@background`, `@at_init`).

- `ZmqStateMachine`
  - Extends `StateMachine` to support remote control via a ZMQ proxy.
    Methods annotated with `@expose_zmq` and `@expose_field_zmq` are
    collected and served over ZMQ. Before calling `run()` on a
    `ZmqStateMachine` you must initialize ZMQ bindings using
    `_initialize_zmq_bindings(vehicle_identifier, proxy_server_addr)` (this
    is typically wired to CLI flags). If bindings are missing `run` will
    raise `StateMachineError`.

## Decorators and helpers

Key decorators and their behavior (see `aerpawlib/v1/runner/decorators.py`):

- `@entrypoint`
  - Marks a single-entry async function for `BasicRunner`.

- `@state(name, first=False)`
  - Marks a standard state method for a `StateMachine`.
  - Attributes added: `_is_state`, `_state_name` (str), `_state_first` (bool),
    `_state_type` set to `_StateType.STANDARD`.

- `@timed_state(name, duration, loop=False, first=False)`
  - Marks a timed state which will run for at least `duration` seconds.
  - Adds the same state markers as `@state` plus `_state_type` set to
    `_StateType.TIMED`, `_state_duration` (float), and `_state_loop` (bool).

- `@expose_zmq(name)` / `@expose_field_zmq(name)`
  - Mark methods to be exposed over the ZMQ control/query API used by
    `ZmqStateMachine`. These set `_is_exposed_zmq` /
    `_is_exposed_field_zmq` and `_zmq_name`.

- `@background`
  - Marks an async method to be executed repeatedly in the background while a
    `StateMachine` is running. Sets `_is_background = True`.

- `@at_init`
  - Marks an async function to run once during vehicle initialization before
    the vehicle is armed. Sets `_run_at_init = True`.

### Internal semantics

- `_StateType`: enum used to distinguish normal and timed states.
- `_State`: internal wrapper that knows how to execute a state function.
  For timed states, `_State.run` starts a background task that repeatedly
  calls the wrapped function (if looping) and then waits for the
  minimum duration. The last returned value from the wrapped function is
  used as the next state's name.

Usage notes
-----------
- Decorated functions are expected to be `async` coroutines; the runners
  will `await` them.
- State functions should return the next state's name (`str`) or `None`
  to finish the state machine.

## Runner implementation notes

Implementation and runtime behavior highlights (from `impl.py`):

- State discovery and execution rely on decorator-set attributes. Decorators
  add attributes such as `_is_state`, `_state_name`, `_state_type`,
  `_state_duration`, etc. The runners treat these as authoritative at
  runtime.
- Timed states are implemented by launching a short-lived background task
  that repeatedly calls the wrapped function (if looping) and then awaiting
  the configured duration before allowing the state's final returned value
  to be used as the next state name.
- Background tasks are scheduled with `asyncio.ensure_future` and are
  automatically restarted if they raise an exception (a short sleep is used
  between restarts). On shutdown these futures are cancelled and awaited to
  ensure a clean stop.
- ZMQ background pub/sub tasks are decorated with `@background` so they
  run alongside the state loop. Messages to remote runners are sent using an
  internal `asyncio.Queue`, and incoming field callbacks are stored and
  awaited by callers of `query_field`.

Errors and exceptions
---------------------
- `NoEntrypointError`: Raised by `BasicRunner` when no `@entrypoint`
  is discovered.
- `NoInitialStateError`: Raised by `StateMachine` when no initial state
  is found.
- `MultipleInitialStatesError`: Raised if more than one state is marked
  as initial.
- `InvalidStateError`: Raised when the state machine transitions to a
  state name that was not discovered during build.
- `StateMachineError`: Miscellaneous configuration/runtime errors.

## Short examples

BasicRunner

```python
class MyScript(BasicRunner):
    @entrypoint
    async def main(self, vehicle: Vehicle):
        await vehicle.takeoff(5)
```

StateMachine

```python
class MySm(StateMachine):
    @state("start", first=True)
    async def start(self, vehicle: Vehicle):
        return "patrol"

    @timed_state("patrol", duration=10)
    async def patrol(self, vehicle: Vehicle):
        return "land"
```

ZmqStateMachine notes

```python
# before run(), call:
self._initialize_zmq_bindings("leader", "127.0.0.1")

# ask another runner for a field (awaitable):
await self.query_field("follower", "position")
```
