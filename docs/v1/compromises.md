# aerpawlib v1: Backward Compatibility & Architecture

The `v1` API of `aerpawlib` is designed to maintain 100% backward compatibility with legacy scripts originally written for the DroneKit-based framework. To achieve this while switching to the modern, `asyncio`-based MAVSDK, several significant architectural compromises were made.

## Dual-Loop Architecture
Legacy user scripts are typically synchronous or expect to control their own execution flow. Modern MAVSDK requires an active `asyncio` event loop for its gRPC communication.

*   Every v1 `Vehicle` instance maintains its own dedicated background thread running a private `asyncio` event loop strictly for MAVSDK operations.
*   This satisfies legacy requirements for synchronous-looking code but adds overhead and complexity in managing thread lifecycles.

## Command Bridging (`_run_on_mavsdk_loop`)
Because MAVSDK methods can only be called from the loop that initialized them, they cannot be called directly from the user's thread.

*   All vehicle commands (arm, takeoff, goto, etc.) must be wrapped in `_run_on_mavsdk_loop`. This function uses `asyncio.run_coroutine_threadsafe` to schedule the command on the background thread and then blocks (or waits via `asyncio.wrap_future`) for the result.
*   While necessary, this creates a slight latency penalty for every command compared to the pure `asyncio` v2 API.

## Thread-Safe Telemetry
Telemtry is received asynchronously on the background thread but read by the user script on the main thread.

*   All internal state variables (position, altitude, heading) are protected by `ThreadSafeValue` wrappers (using `threading.Lock`).
*   Prevents race conditions and partial reads, but adds locking overhead to every telemetry access.

## gRPC Forking Limitations
MAVSDK relies on `grpcio`. gRPC is inherently incompatible with the `fork()` system call in multi-threaded environments (especially on macOS).

*   When legacy scripts use `ExternalProcess` to spawn sub-processes, gRPC detects the background telemetry threads and produces a warning: `Other threads are currently calling into gRPC, skipping fork() handlers`.
*   This is a known cosmetic issue. Users can suppress it by setting `GRPC_ENABLE_FORK_SUPPORT=false` in their environment.

## Blocking Synchronous Connection
DroneKit allowed for static, blocking initialization (`connect("...")`). MAVSDK's `.connect()` is a coroutine.

*   The `v1.Vehicle` constructor calls `_connect_sync()`, which blocks the caller's thread while it spins up the background loop, establishes the MAVLink heartbeat, and waits for the initial telemetry stream to populate.
*   Allows legacy scripts to remain "flat" without needing to be wrapped in an `async def main()` at the entry point level (though most `aerpawlib` scripts are eventually run via `asyncio.run` in the runner).

## 6. Attribute Compatibility Wrappers
DroneKit objects (Battery, GPSInfo, Attitude) were classes with specific attributes, whereas MAVSDK returns named tuples or protobuf-like objects.

*   The `v1` API uses "Compat" classes (`_BatteryCompat`, `_GPSInfoCompat`, etc.) that mimic the exact attribute names and structures of the original DroneKit objects.
*   Ensures that code like `vehicle.battery.level` or `vehicle.gps_0.fix_type` continues to work without modification.

## Manual Task Reaping
In a pure async application, tasks are cleaned up when the loop closes. In v1, the background loop persists across diferentes states.

*   An explicit `close()` method is required to cancel telemetry tasks and stop the background thread. Without this, the process would hang on exit due to the persistent background telemetry thread.
