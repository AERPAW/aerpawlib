# aerpawlib Roadmap

Planned features and improvements for future releases.

## v1 API (Stable, no breaking changes)
- [ ] Integration tests require a running SITL instance; they are not executed in CI and must be
      verified manually before each release (`pytest tests/integration/ --no-sitl-manage`)
- [x] Rover goto commands fixed: raw MAVLink now forces ArduPilot Rover into GUIDED mode before
      arming, resolving the issue where goto commands were accepted only from the MAVProxy console
- [x] ZmqStateMachine race condition fixed: message handling is now sequential (inline `await`)
      instead of spawning concurrent tasks, eliminating ordering hazards on shared state
- [x] ZmqStateMachine malformed-message KeyError fixed: all incoming ZMQ dict fields are now
      accessed via `.get()` with a warning log, matching the v2 behavior


## v2 API (Development)
- [ ] Integration tests require a running SITL instance; they are not executed in CI and must be
      verified manually before each release (`pytest tests/integration/ --no-sitl-manage`)
- [x] Rover goto commands fixed: same GUIDED-mode fix applied as in v1
- [x] ZmqStateMachine race condition and malformed-message handling fixed