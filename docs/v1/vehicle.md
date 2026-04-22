You're not going to be able to write a script without a vehicle.
This module provides the vehicle classes you interact with, which translate your high-level Python commands into the low-level MAVSDK instructions needed to physically fly a drone or drive a rover.


## Example Usage

In practice, the CLI framework creates and passes the vehicle object to your script. All you have to do is fly it.

```python
from aerpawlib.v1 import BasicRunner, Drone, entrypoint

class Mission(BasicRunner):
    @entrypoint
    async def run(self, vehicle: Drone):
        # We start by going up
        await vehicle.takeoff(10)
        
        # We can issue commands using the vehicle's telemetry data
        target = vehicle.position  # We could add a VectorNED here to move
        await vehicle.goto_coordinates(target)
        
        # Bring it home safely
        await vehicle.land()
```

*(Note: The `close()` method is called by the CLI runner during shutdown. If you are ever managing a vehicle lifecycle manually, ensure `close()` is called to properly sever connections and terminate background threads.)*

---

## Error Handling Guide

There are a lot of errors that can be raised by this module especially

### Connectivity and Startup Errors
* `ConnectionTimeoutError`: The MAVSDK background process couldn't talk to the vehicle hardware within the allotted time.
* `AerpawConnectionError`: A broader category for underlying transport, GRPC, or network failures.
* `PortInUseError`: The network port required by the MAVSDK server is already blocked by another process.
* `NotArmableError`: The vehicle failed its preflight safety checks or—crucially for `Drone`s—it powered on and found it was *already armed*, which triggers an immediate shutdown for safety.

### Action Failures
* `ArmError` / `DisarmError`: The vehicle failed to transition into the requested armed/disarmed state.
* `TakeoffError` / `LandingError` / `RTLError`: The hardware rejected or failed to complete standard multirotor commands.
* `NavigationError`: A `goto` command failed, timed out, or was interrupted before completion.
* `VelocityError`: Failed to execute offboard velocity control commands.

### Developer API Errors
* `NotImplementedForVehicleError`: You tried to call a movement API on the base `Vehicle` class instead of a concrete `Drone` or `Rover`.
* `RuntimeError`: Occasionally raised during shutdown if you attempt to send a command while the internal MAVSDK background loop is already tearing down.