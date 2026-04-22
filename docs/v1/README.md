## v1 API Modules

Reference documentation pages used by pdoc for `aerpawlib.v1`.

- `aerpawlib.v1` -> package overview/re-exports
- `aerpawlib.v1.runner` -> `docs/v1/runner.md`
- `aerpawlib.v1.vehicle` -> `docs/v1/vehicle.md`
- `aerpawlib.v1.safety` -> `docs/v1/safety.md`
- `aerpawlib.v1.util` -> `docs/v1/util.md`
- `aerpawlib.v1.aerpaw` -> `docs/v1/aerpaw.md`
- `aerpawlib.v1.constants` -> `docs/v1/constants.md`
- `aerpawlib.v1.exceptions` -> `docs/v1/exceptions.md`
- `aerpawlib.v1.external` -> `docs/v1/external.md`
- `aerpawlib.v1.helpers` -> `docs/v1/helpers.md`
- `aerpawlib.v1.log` -> `docs/v1/log.md`
- `aerpawlib.v1.vehicles` -> `docs/v1/vehicles.md`
- `aerpawlib.v1.zmqutil` -> `docs/v1/zmqutil.md`

Notes:
- `aerpawlib.v1.safetyChecker` is deprecated and intentionally excluded in
  `configs/pdoc.json`.
- The module pages above are included from module docstrings via
  `.. include::` directives so pdoc renders this Markdown as API narrative.

