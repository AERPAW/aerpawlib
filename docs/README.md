# aerpawlib Documentation Overview

This index is the high-level map for aerpawlib documentation.

Hosted API docs: <https://aerpaw.github.io/aerpawlib/>

## Getting Started

| Document | Description |
|---|---|
| [User Guide](USER_GUIDE.md) | Supported workflows and end-to-end script usage |
| [Examples](../examples/) | Runnable example scripts for both v1 and v2 APIs |
| [Tutorials](TUTORIALS.md) | Step-by-step walkthroughs for common tasks |

## Core APIs

| API Version | Description | Reference |
|---|---|---|
| **v1** | Stable, MAVSDK-backed API compatible with legacy aerpawlib usage. | [API Reference](pdoc/aerpawlib/v1.html), [v1 Guide](v1/README.md) |
| **v2** | Async-first API with single-loop architecture and modern runner/safety patterns. | [API Reference](pdoc/aerpawlib/v2.html), [v2 Guide](v2/README.md) |

## Command-Line Interface

The aerpawlib CLI provides script execution, API version selection, logging, and connection management.

- [CLI Usage Guide](CLI.md) – Complete reference for CLI options, configuration, and examples
- See [User Guide](USER_GUIDE.md) for typical command-line workflows

## Advanced Topics

| Document | Audience | Description |
|---|---|---|
| [Development Guide](DEVELOPMENT.md) | Contributors | Project structure, conventions, testing, and tooling |
| [Migration Guide](MIGRATION.md) | Migrating users | v1 to v2 migration notes |
| [Backward Compatibility](ALIASES.md) | Legacy users | Alias modules and where to migrate imports |
| [Roadmap](ROADMAP.md) | All | Planned features and improvements |

## Additional References

- [v1 Safety Checker](v1/safety_checker.md)
- [v1 Architecture Notes](v1/compromises.md)
- [v2 Safety](v2/safety.md)
- [tests/README.md](../tests/README.md)
