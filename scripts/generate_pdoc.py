#!/usr/bin/env python3
"""Generate static pdoc output using repository configuration."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _repo_root() -> Path:
    """Return the repository root path."""
    return Path(__file__).resolve().parent.parent


def _default_config_path() -> Path:
    """Return the default pdoc JSON config path."""
    return _repo_root() / "configs" / "pdoc.json"


def _resolve_from_repo(path_value: str) -> Path:
    """Resolve a potentially relative path from the repository root."""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return _repo_root() / path


def _load_config(config_path: Path) -> Dict[str, Any]:
    """Load and validate the JSON pdoc configuration file."""
    raw = json.loads(config_path.read_text())
    if not isinstance(raw, dict):
        raise TypeError(f"Config at {config_path} must be a JSON object")
    return raw


def _bool_flag(option_name: str, enabled: bool) -> str:
    """Map a config boolean key to pdoc CLI flags."""
    cli_key = option_name.replace("_", "-")
    return f"--{cli_key}" if enabled else f"--no-{cli_key}"


def _build_pdoc_command(config: Dict[str, Any], output_dir: Path) -> List[str]:
    """Build the pdoc CLI command from config."""
    modules = config.get("modules")
    if (
        not isinstance(modules, list)
        or not modules
        or not all(isinstance(module, str) and module for module in modules)
    ):
        raise ValueError("'modules' must be a non-empty list of module strings")

    cmd = [
        sys.executable,
        "-m",
        "pdoc",
        "--output-directory",
        str(output_dir),
    ]

    docformat = config.get("docformat")
    if docformat is not None:
        if not isinstance(docformat, str):
            raise TypeError("'docformat' must be a string when provided")
        cmd.extend(["--docformat", docformat])

    for option in (
        "include_undocumented",
        "search",
        "show_source",
        "math",
        "mermaid",
    ):
        if option in config:
            value = config[option]
            if not isinstance(value, bool):
                raise TypeError(f"'{option}' must be a boolean when provided")
            cmd.append(_bool_flag(option, value))

    for option, cli_name in (
        ("footer_text", "--footer-text"),
        ("favicon", "--favicon"),
        ("logo", "--logo"),
        ("logo_link", "--logo-link"),
    ):
        value = config.get(option)
        if value is not None:
            if not isinstance(value, str):
                raise TypeError(f"'{option}' must be a string when provided")
            cmd.extend([cli_name, value])

    edit_url = config.get("edit_url")
    if edit_url is not None:
        if not isinstance(edit_url, dict):
            raise TypeError("'edit_url' must be an object mapping module -> URL")
        for module, url in edit_url.items():
            if not isinstance(module, str) or not isinstance(url, str):
                raise TypeError("'edit_url' keys and values must be strings")
            cmd.extend(["--edit-url", f"{module}={url}"])

    cmd.extend(modules)
    return cmd


def main() -> int:
    """CLI entry point for generating pdoc documentation."""
    parser = argparse.ArgumentParser(description="Generate pdoc API documentation")
    parser.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="Path to pdoc JSON config (default: configs/pdoc.json)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete output directory before rendering docs",
    )
    args = parser.parse_args()

    config_path = _resolve_from_repo(args.config)
    if not config_path.exists():
        raise FileNotFoundError(f"pdoc config not found: {config_path}")

    config = _load_config(config_path)
    output_dir_raw = config.get("output_directory", "docs/pdoc")
    if not isinstance(output_dir_raw, str):
        raise TypeError("'output_directory' must be a string")
    output_dir = _resolve_from_repo(output_dir_raw)

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = _build_pdoc_command(config, output_dir)
    subprocess.run(command, check=True, cwd=_repo_root())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
