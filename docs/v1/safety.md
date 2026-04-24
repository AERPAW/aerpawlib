When you're operating autonomous vehicles, having robust guardrails is non-negotiable. This module provides a highly resilient client/server architecture designed to validate your mission commands against strict environmental and vehicle constraints—like geofences, speed limits, and altitude bounds, *before* the vehicle ever makes a move.

Here is a breakdown of how the safety checker works, how to configure it, and how to wire it into your mission logic.

## The Architecture at a Glance

The safety module splits the workload between two primary components, communicating over a strictly enforced ZeroMQ (ZMQ) REQ/REP pattern:

### `SafetyCheckerClient`
This is your mission script's direct line to the safety authority. It acts as a ZMQ REQ client that asks for permission before executing maneuvers. 
* **Resiliency built-in:** Networks aren't perfect. If the server takes too long to reply, the client will raise a `TimeoutError`. But pragmatically, it also automatically resets and reconnects its socket so that subsequent requests can still succeed without restarting your entire script.

### `SafetyCheckerServer`
This is the central authority. It runs a blocking ZMQ REP server that loads your safety configuration from a YAML file. 
* **The Enforcer:** It evaluates every incoming request against your defined include/exclude geofences, speed limits, and (for copters) altitude bounds. It also remembers your takeoff point to validate landing distances later on.
---

## What You Can Ask the Server

The safety protocol routes requests using specific constants defined in `aerpawlib.v1.constants`. Under the hood, `SafetyCheckerServer.REQUEST_FUNCTIONS` maps these to their respective validation logic:

* `server_status_req`
* `validate_waypoint_req`
* `validate_change_speed_req`
* `validate_takeoff_req`
* `validate_landing_req`

---

## Putting It Into Practice

Using the safety checker in your code is straightforward. You instantiate the client, perform a status check, and then validate your commands before executing them. 

*Note: Validation methods return a tuple of `(result: bool, message: str)`. Always check the result before proceeding.*

```python
from aerpawlib.v1 import Coordinate
from aerpawlib.v1.safety import SafetyCheckerClient

# Connect to the local safety server
with SafetyCheckerClient("127.0.0.1", 14580) as checker:
    # Always ensure the server is alive and happy first
    ok, msg = checker.check_server_status()
    if not ok:
        raise RuntimeError(f"Safety server is not ready: {msg}")

    cur = Coordinate(35.7275, -78.6960, 10)
    nxt = Coordinate(35.7280, -78.6955, 15)
    
    # Ask permission to move
    ok, msg = checker.validate_waypoint_command(cur, nxt)
    if not ok:
        print(f"Maneuver rejected by safety constraints: {msg}")
        # Handle the rejection (e.g., transition to a loiter or RTL state)
```

---

## Configuring the Server

The `SafetyCheckerServer` expects a YAML file defining the strict limits for the vehicle. Note that geofence paths (KML files) are resolved relative to where this YAML file lives.

**Required for all vehicles:**
* `vehicle_type`: Must be `copter` or `rover`.
* `max_speed` / `min_speed`: Absolute speed limits.
* `include_geofences`: KML paths defining where the vehicle *must* stay.
* `exclude_geofences`: KML paths defining where the vehicle *cannot* go.

**Required exclusively for `copter`:**
* `max_alt` / `min_alt`: Absolute altitude limits.

*(Note: If your configuration is missing keys or has an invalid vehicle type, the server will raise a generic `Exception` during startup, failing fast so you can fix it.)*

---

## Errors and Rejections

When writing robust code, you have to plan for failures. Here is how the module handles them:

### Client-Side Issues
* **`TimeoutError`:** Raised by `send_request(...)` if the server goes dark. As mentioned, the client handles the socket cleanup automatically.
* **`ValueError`:** Raised by `deserialize_msg(...)` if the client receives a malformed compressed payload or invalid JSON.

### Server-Side Protections
* **Graceful Rejections:** If you send an unknown request function or if the server encounters an unexpected exception while handling a valid request, it won't crash. It simply catches the error and returns a safe `(False, "error message")` response.
* **Stateful Validation:** If you ask the server to validate a landing command, but you never recorded a takeoff point, the validation will fail outright.

---

## Implementation Details

If you are digging into the source code, here are a few structural choices to keep in mind:
* The `SafetyCheckerServer` initiates its blocking loop directly inside `__init__`.
* Because ZMQ REQ/REP is a strict lock-step pattern, every single request *must* receive exactly one reply to prevent the socket from hanging.
* Waypoint validation isn't just checking points; it tests the actual path. It uses polygon-edge intersection math (`_polygon_edges(...)` and `do_intersect(...)`) to ensure the line drawn between your current position and the next waypoint doesn't clip a no-fly zone.

---

## CLI and Legacy Notes

You can spin up the server directly from the command line using the provided CLI entry point:

```bash
python -m aerpawlib.v1.safety --port 14580 --vehicle_config config.yaml
```

**Deprecation Warning:** You may see older code using `aerpawlib.v1.safetyChecker`. This is a legacy alias that is strictly deprecated. Always use `aerpawlib.v1.safety` for new development to ensure future compatibility.