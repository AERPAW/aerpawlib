"""Progress bar utilities for aerpawlib CLI."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()
_progress: Progress | None = None
_task_id: Any = None
_enabled: bool = False


def is_enabled() -> bool:
    """Check if progress bar is enabled."""
    return _enabled


def start_progress(enabled: bool = True) -> None:
    """Start the progress bar if enabled."""
    global _progress, _task_id, _enabled
    _enabled = enabled and sys.stdout.isatty()
    if not _enabled:
        return
    if _progress is None:
        _progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("[bold dim]│[/bold dim] [bold cyan]Phase: {task.fields[phase]}[/bold cyan]"),
            TextColumn("{task.fields[state]}"),
            TextColumn("[bold dim]│[/bold dim] [bold green]Mode: {task.fields[mode]}[/bold green]"),
            TextColumn("[bold dim]│[/bold dim] {task.fields[armed]}"),
            TextColumn("[bold dim]│[/bold dim] {task.fields[battery]}"),
            TextColumn("[bold dim]│[/bold dim] {task.fields[sats]}"),
            TextColumn("[bold dim]│[/bold dim] {task.fields[altitude]}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        _progress.start()
        _task_id = _progress.add_task(
            "Preparing...",
            total=100,
            phase="Startup",
            state="",
            mode="UNKNOWN",
            armed="[bold red]Disarmed[/bold red]",
            battery="[bold yellow]Power: --%[/bold yellow]",
            sats="[bold blue]Sats: --[/bold blue]",
            altitude="[bold green]Alt: 0.0m[/bold green]",
        )


def update_progress(
    description: str,
    advance: float = 0,
    completed: float | None = None,
    phase: str | None = None,
    state: str | None = None,
) -> None:
    """Update description and completion status of the progress bar."""
    global _progress, _task_id, _enabled
    if not _enabled or _progress is None or _task_id is None:
        return

    # Map completion percentage to experiment phase
    if phase is None and completed is not None:
        if completed < 60:
            phase = "Startup"
        elif completed < 90:
            phase = "Experiment"
        else:
            phase = "Teardown"

    if phase is not None:
        phase = phase.capitalize()

    kwargs: dict[str, Any] = {"description": description, "advance": advance}
    if completed is not None:
        kwargs["completed"] = completed
    if phase is not None:
        kwargs["phase"] = phase
    if state is not None:
        kwargs["state"] = f" [bold dim]│[/bold dim] [bold magenta]State: {state}[/bold magenta]"

    _progress.update(_task_id, **kwargs)


def update_telemetry(
    armed: bool | None = None,
    battery: int | None = None,
    sats: int | None = None,
    altitude: float | None = None,
    mode: str | None = None,
) -> None:
    """Update the real-time telemetry variables shown on the progress bar."""
    global _progress, _task_id, _enabled
    if not _enabled or _progress is None or _task_id is None:
        return

    kwargs: dict[str, Any] = {}
    if armed is not None:
        kwargs["armed"] = "[bold green]Armed[/bold green]" if armed else "[bold red]Disarmed[/bold red]"
    if battery is not None:
        kwargs["battery"] = f"[bold yellow]Power: {battery}%[/bold yellow]"
    if sats is not None:
        kwargs["sats"] = f"[bold blue]Sats: {sats}[/bold blue]"
    if altitude is not None:
        kwargs["altitude"] = f"[bold green]Alt: {altitude:.1f}m[/bold green]"
    if mode is not None:
        kwargs["mode"] = mode

    _progress.update(_task_id, **kwargs)


def stop_progress() -> None:
    """Stop the progress bar and clean up."""
    global _progress, _task_id, _enabled
    if _progress is not None:
        _progress.stop()
        _progress = None
        _task_id = None
    _enabled = False
