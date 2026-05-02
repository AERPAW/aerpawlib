"""Resolve CLI filesystem paths relative to the
directory the user invoked the CLI from."""
from __future__ import annotations

from pathlib import Path


def find_repo_root_containing_examples() -> str | None:
    """If *aerpawlib* is installed under a checkout that has ``examples/``,
    return that root.

    When the package lives only under ``site-packages`` (no sibling
    ``examples/``), returns ``None`` so callers can fall back to other
    heuristics.
    """
    cli_dir = Path(__file__).resolve().parent
    pkg_dir = cli_dir.parent
    repo = pkg_dir.parent
    if (repo / "examples").is_dir() and (repo / "aerpawlib").is_dir():
        return str(repo)
    return None


def _resolve_cli_path_obj(
    path: str | None, invocation_cwd: str) -> Path | None:
    """Internal: resolve path, returning Path object."""
    if path is None:
        return None
    if path == "":
        return None
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.absolute()
    return (Path(invocation_cwd) / candidate).absolute()


def resolve_script_path(relative: str, invocation_cwd: str) -> str:
    """Resolve a script path: first against *invocation_cwd*,
    then against the repo root if needed."""
    p = _resolve_cli_path_obj(relative, invocation_cwd)
    if p and p.is_file():
        return str(p)
    if Path(relative).is_absolute():
        return str(p) if p else relative
    repo = find_repo_root_containing_examples()
    if repo:
        p2 = (Path(repo) / relative).absolute()
        if p2.is_file():
            return str(p2)
    return str(p) if p else relative


def resolve_cli_path(path: str | None, invocation_cwd: str) -> Path:
    """If path is relative, resolve it against invocation_cwd
    Returns normalized absolute Path object.
    Raises ValueError if path is None or empty.
    """
    if path is None or path == "":
        raise ValueError(f"Invalid path: {path!r}")
    p = _resolve_cli_path_obj(path, invocation_cwd)
    if p is None:
        raise ValueError(f"Could not resolve path: {path}")
    return p
