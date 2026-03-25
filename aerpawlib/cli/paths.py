"""Resolve CLI filesystem paths relative to the directory the user invoked the CLI from."""

import os
from pathlib import Path
from typing import Optional


def find_repo_root_containing_examples() -> Optional[str]:
    """If *aerpawlib* is installed under a checkout that has ``examples/``, return that root.

    When the package lives only under ``site-packages`` (no sibling ``examples/``), returns
    ``None`` so callers can fall back to other heuristics.
    """
    cli_dir = Path(__file__).resolve().parent
    pkg_dir = cli_dir.parent
    repo = pkg_dir.parent
    if (repo / "examples").is_dir() and (repo / "aerpawlib").is_dir():
        return str(repo)
    return None


def resolve_script_path(relative: str, invocation_cwd: str) -> str:
    """Resolve a script path: first against *invocation_cwd*, then against the repo root if needed."""
    p = resolve_cli_path(relative, invocation_cwd)
    if os.path.isfile(p):
        return p
    if os.path.isabs(relative):
        return p
    repo = find_repo_root_containing_examples()
    if repo:
        p2 = os.path.normpath(os.path.join(repo, relative))
        if os.path.isfile(p2):
            return p2
    return p


def resolve_cli_path(path: Optional[str], invocation_cwd: str) -> Optional[str]:
    """If *path* is relative, resolve it against *invocation_cwd*; return normalized absolute path."""
    if path is None or path == "":
        return path
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(invocation_cwd, path))
