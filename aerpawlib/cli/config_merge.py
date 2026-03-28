"""Merge JSON config files into synthetic CLI argv."""

import json
from typing import Any

from aerpawlib.cli.constants import CONFIG_ARG_PAIR_SIZE


def strip_config_argv(argv: list[str]) -> list[str]:
    """Remove --config PATH and --config=PATH tokens from argv."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config" and i + 1 < len(argv):
            i += CONFIG_ARG_PAIR_SIZE
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
        with open(path, "r") as f:
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
