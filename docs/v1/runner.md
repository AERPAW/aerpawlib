## Overview

Operating autonomous vehicles means handling a lot of concurrent logic. This module provides the core runner implementations and decorators you need to build v1 missions in `aerpawlib`. 

Whether you want to write a straightforward, single-entry script or a highly complex, multi-vehicle state machine, this module handles the underlying execution flow so you can focus on your experiment's logic.

## The Runner Architecture

At the highest level, all scripts in `aerpawlib` are built on a foundational `Runner` class. Subclasses of `Runner` dictate your script's execution model and provide optional hooks like `initialize_args` and `cleanup`. 

When you're ready to write your mission logic, you'll choose one of these three implementations:

### `BasicRunner`
For simple scripts where you want to manually control the entire flow of the program, `BasicRunner` is your pragmatic, go-to choice. 
* **How it works:** It looks for a single method in your script decorated with `@entrypoint` and executes it. 
* **Guardrails:** If you accidentally include multiple entrypoints, it will raise a `StateMachineError` to prevent spaghetti logic. If you forget to include an entrypoint entirely, you'll get a `NoEntrypointError`.


### `StateMachine`
When your experiment logic gets more complex, `StateMachine` is the powerhouse framework. It allows you to build a map of distinct "states" and seamlessly transition between them.
* **How it works:** You decorate your methods with `@state` or `@timed_state`. The state machine `await`s the current state's function, and whatever string you return becomes the next state it executes. 
* **Initialization:** You *must* tell the runner where to start by marking exactly one state with `first=True`. If you don't, it raises a `NoInitialStateError`. If you mark more than one, you'll trigger a `MultipleInitialStatesError`.

### `ZmqStateMachine`
Multi-vehicle control software is inherently difficult. `ZmqStateMachine` extends the standard state machine to support remote control and synchronization via a ZeroMQ (ZMQ) proxy. 
* **How it works:** It collects any methods you've annotated with `@expose_zmq` and `@expose_field_zmq` and serves them over ZMQ, allowing other vehicles or a ground station to trigger transitions or query data.
* **Important Setup:** Before calling `run()` on a `ZmqStateMachine`, you must initialize the ZMQ bindings using `_initialize_zmq_bindings(vehicle_identifier, proxy_server_addr)`—this is typically wired up via CLI flags. If you forget this step, `run()` will immediately raise a `StateMachineError`.

---

## Available Decorators

To make defining your mission logic as clean and Pythonic as possible, `aerpawlib` relies heavily on decorators. 

**A quick note on async:** Decorated functions are expected to be `async` coroutines, as the runners will inherently `await` them. State functions should always return the next state's name as a string, or `None` if the mission is complete.

* `@entrypoint`: Your starting line. Marks a single-entry async function for `BasicRunner`.
* `@state(name, first=False)`: Defines a standard state for a `StateMachine`. 
* `@timed_state(name, duration, loop=False, first=False)`: A highly useful decorator that guarantees a state runs for *at least* the allotted `duration` (in seconds) before transitioning. 
* `@background`: Marks an async method to run repeatedly in the background while your state machine is active. This is perfect for continuous tasks like logging telemetry.
* `@at_init`: Marks an async function that needs to run exactly once during vehicle initialization, *before* the vehicle is armed.
* `@expose_zmq(name)` / `@expose_field_zmq(name)`: Opens up methods to the ZMQ control/query API, allowing for multi-vehicle coordination.

---

## Implementation Details

You usually don't need to worry about how `aerpawlib` manages state internally, but if you are debugging or writing advanced logic, here is what is happening behind the scenes:

* The runners treat decorator-injected attributes as the ultimate source of truth at runtime. Decorators silently add attributes to your methods like `_is_state`, `_state_name`, `_state_type` (which distinguishes standard vs. timed states), and `_state_duration`. 
* When you use `@timed_state`, the internal `_State` wrapper launches a short-lived background task. It repeatedly calls your wrapped function (if `loop=True`) and then strictly waits for the configured duration. Only the *last* returned value from your function is passed along as the next state name.
* Background tasks are scheduled via `asyncio.ensure_future`. If your background task hits a snag and raises an exception, `aerpawlib` will automatically catch the exception, sleep briefly, and restart the task. On shutdown, all futures are safely cancelled and awaited for a clean exit.
* Background pub/sub tasks for ZMQ are actually just decorated with `@background`, meaning they run neatly alongside your main state loop. Messages to remote runners are queued up via `asyncio.Queue`, and incoming callbacks are safely stored and awaited when you call `query_field`.

---

## Error Handling Guide

`aerpawlib` uses specific exceptions to help you catch configuration and logic bugs early:

* `NoEntrypointError`: Your `BasicRunner` can't find its `@entrypoint`.
* `NoInitialStateError`: Your `StateMachine` doesn't know where to start (missing `first=True`).
* `MultipleInitialStatesError`: You've accidentally set `first=True` on more than one state.
* `InvalidStateError`: You returned a state name that doesn't exist (e.g., returning `"go_north"` when the state is actually named `"fly_north"`).
* `StateMachineError`: A catch-all for various runtime or configuration issues (like forgetting to initialize ZMQ bindings).

---

## Quick Reference Examples

### BasicRunner
```python
class MyScript(BasicRunner):
    @entrypoint
    async def main(self, vehicle: Vehicle):
        # We take off, and we're done! Simple and clean.
        await vehicle.takeoff(5)
```

### StateMachine
```python
class MySm(StateMachine):
    @state(name="start", first=True)
    async def start(self, vehicle: Vehicle):
        # Setup complete, let's move to the patrol state
        return "patrol"

    @timed_state(name="patrol", duration=10)
    async def patrol(self, vehicle: Vehicle):
        # This state is guaranteed to hold for 10 seconds
        # before the runner accepts "land" and transitions.
        return "land"
```

### ZmqStateMachine
```python
# During setup, before calling run():
self._initialize_zmq_bindings("leader", "127.0.0.1")

# Inside your state, asking another runner for a data field:
target_coords = await self.query_field("follower", "position")
```