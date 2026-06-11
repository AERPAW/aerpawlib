"""Progress bar utilities for aerpawlib CLI."""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()
_progress: Progress | None = None
_task_id: Any = None
_enabled: bool = False

_GPS_FIX_LABELS = {
    0: "No fix",
    1: "No fix",
    2: "2D",
    3: "3D",
    4: "DGPS",
    5: "RTK",
    6: "RTK",
}


@dataclass
class _StatusFields:
    description: str = "Preparing..."
    phase: str = "Startup"
    state: str = ""
    mode: str = "UNKNOWN"
    armed: bool | None = None
    battery: int | None = None
    voltage: float | None = None
    sats: int | None = None
    gps_fix: int | None = None
    altitude: float | None = None
    heading: float | None = None
    speed: float | None = None


_status = _StatusFields()
_TELEMETRY_REFRESH_INTERVAL_S = 0.1
_last_telemetry_refresh = 0.0


def is_enabled() -> bool:
    """Check if progress bar is enabled."""
    return _enabled


def _gps_fix_label(fix_type: int) -> str:
    return _GPS_FIX_LABELS.get(fix_type, f"fix {fix_type}")


def _format_line() -> str:
    parts: list[str] = [f"[bold]{_status.description}[/bold]"]
    parts.append(f"[cyan]{_status.phase}[/cyan]")
    if _status.state:
        parts.append(f"[magenta]{_status.state}[/magenta]")
    if _status.mode != "UNKNOWN":
        parts.append(f"[green]{_status.mode}[/green]")
    if _status.armed is not None:
        parts.append(
            "[green]Armed[/green]" if _status.armed else "[red]Disarmed[/red]",
        )
    if _status.battery is not None:
        if _status.battery > 20:
            batt_style = "yellow"
        elif _status.battery > 10:
            batt_style = "dark_orange"
        else:
            batt_style = "red"
        parts.append(f"[{batt_style}]{_status.battery}%[/{batt_style}]")
    if _status.voltage is not None:
        parts.append(f"[yellow]{_status.voltage:.1f}V[/yellow]")
    if _status.gps_fix is not None:
        parts.append(f"[blue]{_gps_fix_label(_status.gps_fix)}[/blue]")
    if _status.sats is not None:
        parts.append(f"[blue]{_status.sats} sats[/blue]")
    if _status.altitude is not None:
        parts.append(f"[green]{_status.altitude:.1f} m[/green]")
    if _status.heading is not None:
        parts.append(f"[cyan]{_status.heading:.0f}°[/cyan]")
    if _status.speed is not None:
        parts.append(f"[cyan]{_status.speed:.1f} m/s[/cyan]")
    return " · ".join(parts)


def _refresh() -> None:
    if _progress is not None and _task_id is not None:
        _progress.update(_task_id, line=_format_line())


def start_progress(enabled: bool = True) -> None:
    """Start the progress bar if enabled."""
    global _progress, _task_id, _enabled, _status
    _enabled = enabled and sys.stdout.isatty()
    if not _enabled:
        return
    _status = _StatusFields()
    if _progress is None:
        _progress = Progress(
            SpinnerColumn(spinner_name="dots", style="cyan"),
            TextColumn("{task.fields[line]}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        _progress.start()
        _task_id = _progress.add_task("", line=_format_line())


def update_progress(
    description: str | None = None,
    advance: float = 0,
    completed: float | None = None,
    phase: str | None = None,
    state: str | None = None,
) -> None:
    """Update description and completion status of the progress bar."""
    global _enabled
    if not _enabled or _progress is None or _task_id is None:
        return

    if phase is None and completed is not None:
        if completed < 60:
            phase = "Startup"
        elif completed < 90:
            phase = "Experiment"
        else:
            phase = "Teardown"

    if description is not None:
        _status.description = description
    if phase is not None:
        _status.phase = phase.capitalize()
    if state is not None:
        _status.state = state

    _refresh()


def update_telemetry(
    armed: bool | None = None,
    battery: int | None = None,
    voltage: float | None = None,
    sats: int | None = None,
    gps_fix: int | None = None,
    altitude: float | None = None,
    heading: float | None = None,
    speed: float | None = None,
    mode: str | None = None,
    *,
    velocity_ned: tuple[float, float, float] | None = None,
) -> None:
    """Update the real-time telemetry variables shown on the progress bar."""
    global _enabled, _last_telemetry_refresh
    if not _enabled or _progress is None or _task_id is None:
        return

    if armed is not None:
        _status.armed = armed
    if battery is not None:
        _status.battery = battery
    if voltage is not None:
        _status.voltage = voltage
    if sats is not None:
        _status.sats = sats
    if gps_fix is not None:
        _status.gps_fix = gps_fix
    if altitude is not None:
        _status.altitude = altitude
    if heading is not None:
        _status.heading = heading % 360
    if speed is not None:
        _status.speed = speed
    elif velocity_ned is not None:
        north, east, _down = velocity_ned
        _status.speed = math.hypot(north, east)
    if mode is not None:
        _status.mode = mode

    now = time.monotonic()
    if now - _last_telemetry_refresh >= _TELEMETRY_REFRESH_INTERVAL_S:
        _last_telemetry_refresh = now
        _refresh()


def stop_progress() -> None:
    """Stop the progress bar and clean up."""
    global _progress, _task_id, _enabled, _status, _last_telemetry_refresh
    if _enabled and _progress is not None and _task_id is not None:
        _refresh()
    if _progress is not None:
        _progress.stop()
        _progress = None
        _task_id = None
    _status = _StatusFields()
    _last_telemetry_refresh = 0.0
    _enabled = False
