"""Shared end-of-mission RTL helper for v1 and v2 experiment runners."""

from __future__ import annotations

import logging
from typing import Any

from aerpawlib.cli.constants import VEHICLE_TYPE_DRONE, VEHICLE_TYPE_ROVER

logger = logging.getLogger("aerpawlib")


async def return_home_if_armed(
    vehicle: Any,
    vehicle_type: str,
    rtl_at_end: bool,
    reason: str = "experiment ending",
) -> None:
    """RTL/RTH when the vehicle is still armed at successful end, unless ``--skip-rtl``.

    Callers must not invoke this on failure, Ctrl-C, or heartbeat loss. Old
    aerpawlib only RTLd after ``runner.run()`` returned normally.
    """
    if not rtl_at_end or vehicle is None:
        return
    if getattr(vehicle, "closed", False) or not getattr(vehicle, "armed", False):
        return
    from aerpawlib.cli.progress_bar import update_progress

    update_progress(f"Vehicle still armed ({reason})! Returning home...", completed=90)
    logger.warning("Vehicle still armed (%s)! Returning home...", reason)
    try:
        if vehicle_type == VEHICLE_TYPE_DRONE:
            await vehicle.return_to_launch()
        elif vehicle_type == VEHICLE_TYPE_ROVER and getattr(vehicle, "home_coords", None):
            await vehicle.goto_coordinates(vehicle.home_coords)
    except Exception as e:
        logger.error("Return home failed: %s", e)
