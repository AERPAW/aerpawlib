# Backward-Compatible Alias Modules

`aerpawlib` keeps a small set of compatibility aliases so older scripts keep working.
New code should import from explicit versioned namespaces (`aerpawlib.v1` or `aerpawlib.v2`).

## Top-level aliases

| Alias module              | Preferred imports                                  |
|---------------------------|----------------------------------------------------|
| `aerpawlib.runner`        | `aerpawlib.v1.runner` or `aerpawlib.v2.runner`     |
| `aerpawlib.vehicle`       | `aerpawlib.v1.vehicle` or `aerpawlib.v2.vehicle`   |
| `aerpawlib.external`      | `aerpawlib.v1.external` or `aerpawlib.v2.external` |
| `aerpawlib.aerpaw`        | `aerpawlib.v1.aerpaw` or `aerpawlib.v2.aerpaw`     |
| `aerpawlib.zmqutil`       | `aerpawlib.v1.zmqutil` or `aerpawlib.v2.zmqutil`   |
| `aerpawlib.safetyChecker` | `aerpawlib.v1.safety` or `aerpawlib.v2.safety`     |

## v1 alias module

| Alias module                 | Preferred import      |
|------------------------------|-----------------------|
| `aerpawlib.v1.safetyChecker` | `aerpawlib.v1.safety` |

## Documentation behavior

The generated pdoc site hides these compatibility alias modules so the primary
docs navigation stays focused on v1, v2, and CLI.
