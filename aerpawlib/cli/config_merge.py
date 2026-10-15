"""Merge JSON config files into synthetic CLI argv."""

import json
from pathlib import Path
from typing import Any

BOOLEAN_CLI_OPTIONS = frozenset(
    {
        "skip-init",
        "skip-rtl",
        "no-aerpaw-environment",
        "verbose",
        "quiet",
        "no-aerpawlib-stdout",
        "no-status-bar",
    },
)
"""aerpawlib CLI flags that take no value. A config value must be a boolean."""

_FALSE_STRINGS = frozenset({"false", "0", "no"})
_TRUE_STRINGS = frozenset({"true", "1", "yes"})


def _config_bool(key: str, value: Any) -> bool:
    """Interpret a config value for a boolean flag, rejecting anything ambiguous.

    ``--skip-rtl false`` would *enable* the flag (Typer flags take no value),
    so ``"false"`` / ``"0"`` / ``"no"`` must mean False rather than being
    stringified onto argv.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _FALSE_STRINGS:
            return False
        if lowered in _TRUE_STRINGS:
            return True
    raise ValueError(
        f"Config option {key!r} is a boolean flag; use JSON true/false (got {value!r})",
    )


def strip_config_argv(argv: list[str]) -> list[str]:
    """Remove --config PATH and --config=PATH tokens from argv."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config" and i + 1 < len(argv):
            i += 2
            continue
        if arg.startswith("--config="):
            i += 1
            continue
        out.append(arg)
        i += 1
    return out


def merge_config_json_files(paths: list[str]) -> dict[str, Any]:
    """
    Load JSON config files in order. Later files override earlier keys.
    JSON null for a key removes it from the merged result (no flag emitted).
    """
    merged: dict[str, Any] = {}
    for path in paths:
        with Path(path).open() as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Config must be a JSON object: {path}")
        for key, value in data.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
    return merged


def config_dict_to_cli_args(config_data: dict[str, Any]) -> list[str]:
    """Turn merged JSON config into fake argv tokens for argparse."""
    config_cli_args: list[str] = []
    for key, value in config_data.items():
        if key in BOOLEAN_CLI_OPTIONS:
            if value is not None and _config_bool(key, value):
                config_cli_args.append(f"--{key}")
            continue
        if isinstance(value, bool) or value is None:
            if value:
                config_cli_args.append(f"--{key}")
        elif isinstance(value, list):
            for item in value:
                config_cli_args.append(f"--{key}")
                config_cli_args.append(str(item))
        else:
            config_cli_args.append(f"--{key}")
            config_cli_args.append(str(value))
    return config_cli_args
