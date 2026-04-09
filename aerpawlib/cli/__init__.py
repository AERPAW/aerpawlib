"""
CLI support package for the ``aerpawlib`` command.

This package contains parsing and execution helpers used by
``aerpawlib.__main__.main``.

Typical usage:

    aerpawlib --script my_mission.py --conn udpin://127.0.0.1:14550 --vehicle drone

Important flags:
- ``--api-version``: choose ``v1`` or ``v2`` runtime behavior.
- ``--config``: merge one or more JSON config files into CLI defaults.
- ``--structured-log``: emit JSONL mission and telemetry events.
- ``--run-proxy``: run the ZMQ relay for multi-vehicle state-machine flows.

For a task-oriented usage guide, see ``docs/CLI.md``.
"""
