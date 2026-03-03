# v1 vs v2 Feature Parity

| Feature                                                  | v1       | v2           |
|----------------------------------------------------------|----------|--------------|
| Drone                                                    | Yes      | Yes          |
| Rover                                                    | Yes      | Yes          |
| DummyVehicle                                             | Yes      | Yes          |
| BasicRunner                                              | Yes      | Yes          |
| StateMachine                                             | Yes      | Yes          |
| ZmqStateMachine                                          | Yes      | Yes          |
| `@entrypoint`                                            | Yes      | Yes          |
| `@state`, `@timed_state`                                 | Yes      | Yes          |
| `@background`, `@at_init`                                | Yes      | Yes          |
| `@expose_zmq`, `@expose_field_zmq`                       | Yes      | Yes          |
| Coordinate                                               | Yes      | Yes          |
| VectorNED                                                | Yes      | Yes          |
| VectorNED.cross_product                                  | Yes      | Yes          |
| read_from_plan                                           | Yes      | Yes          |
| read_from_plan_complete                                  | Yes      | Yes          |
| get_location_from_waypoint                               | Yes      | Yes          |
| Geofence (read_geofence, inside, do_intersect)           | Yes      | Yes          |
| SafetyCheckerClient/Server                               | Yes      | Yes          |
| Command validation (can_takeoff, can_goto, can_land)     | No       | Yes          |
| vehicle.safety integration                               | No       | Yes          |
| Config dataclass (BasicRunnerConfig, StateMachineConfig) | No       | Yes          |
| Non-blocking goto (VehicleTask)                          | No       | Yes          |
| Connection                                               | Blocking | Async        |
