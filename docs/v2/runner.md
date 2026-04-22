## Overview

Runners are how aerpawlib turns a Python class into a mission. v2 uses descriptor-based decorators and optional `config` dataclasses: you write async methods, attach `@entrypoint` or `@state`, and the implementation schedules them on the same event loop that drives the vehicle.

This package re-exports `BasicRunner`, `StateMachine`, and `ZmqStateMachine` from `impl`, plus all decorators and config types from `config` and `decorators`.

### Runner types
- `BasicRunner`:  one coroutine marked with `@entrypoint`. Good for straight-line experiments and examples.
- `StateMachine`:  many `@state` / `@timed_state` methods that return the next state name, optional `@background` coroutines, and `@at_init` hooks that run before the first state.
- `ZmqStateMachine`:  like `StateMachine` but also registers ZMQ entrypoints for remote `transition_runner` and `query_field` among brokers and peers. Requires proxy setup and identifier flags from the CLI.

### Config vs decorators
- You can rely entirely on decorators (the usual path for examples).
- Or set `config = BasicRunnerConfig(...)` / `StateMachineConfig` / `ZmqStateMachineConfig` on the class to name entrypoints and states without relying on attribute scanning in edge cases.

### ZMQ
- Run the proxy first (`aerpawlib --run-proxy` or the helper in [zmqutil](zmqutil.md)), then launch runners with matching `--zmq-identifier` and `--zmq-proxy-server`.

### Error handling
- Misconfigured runners raise the `RunnerError` family (`NoEntrypointError`, `NoInitialStateError`, `InvalidStateError`, and similar). See [exceptions](exceptions.md).

The [v2 README](README.md) has end-to-end snippets for each runner style and a decorator reference table; use that for copy-pastable mission skeletons.
