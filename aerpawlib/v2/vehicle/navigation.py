"""Shared navigation helpers for v2 Drone and Rover (internal)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from aerpawlib.v2.constants import (
    GOTO_LOG_INTERVAL_S,
    GOTO_NB_LOG_INTERVAL_S,
    POLLING_DELAY_S,
)
from aerpawlib.v2.exceptions import NavigationError
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.types import Coordinate, VectorNED

from .connection_helpers import _wait_for_condition
from .task import VehicleTask

if TYPE_CHECKING:
    from .base import Vehicle

logger = get_logger(LogComponent.VEHICLE)


async def wait_for_blocking_goto(
    vehicle: Vehicle,
    coordinates: Coordinate,
    *,
    distance_fn: Callable[[], float],
    tolerance: float,
    timeout: float,
    log_prefix: str,
) -> None:
    """Poll until the vehicle arrives at ``coordinates`` or times out."""
    start = time.monotonic()
    last_log = 0.0
    while not vehicle.done_moving():
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise TimeoutError(f"{log_prefix}goto timed out within {timeout}s")
        now = time.monotonic()
        if now - last_log >= GOTO_LOG_INTERVAL_S:
            dist = distance_fn(coordinates)
            logger.debug(
                "%s: goto_coordinates progress dist=%.1fm tol=%.1fm elapsed=%.0fs",
                log_prefix,
                dist,
                tolerance,
                elapsed,
            )
            last_log = now
        await asyncio.sleep(POLLING_DELAY_S)


def start_nonblocking_goto(
    vehicle: Vehicle,
    coordinates: Coordinate,
    *,
    distance_fn: Callable[[], float],
    tolerance: float,
    timeout: float,
    on_cancel: Callable[[], Awaitable[None]],
    log_prefix: str,
    progress_poll_interval: float = 0.2,
    on_complete: Callable[[], None] | None = None,
) -> VehicleTask:
    """Return a VehicleTask tracking non-blocking goto progress."""
    handle = VehicleTask()
    logger.debug("%s: goto_coordinates returning non-blocking VehicleTask", log_prefix)
    handle.set_on_cancel(on_cancel)

    initial_dist = distance_fn(coordinates)

    async def _wait_arrival() -> None:
        try:
            await _wait_for_condition(
                lambda: vehicle.done_moving() or handle.is_cancelled(),
                timeout=timeout,
            )
            if handle.is_cancelled():
                handle.set_complete()
                return
            if on_complete is not None:
                on_complete()
            handle.set_progress(1.0)
            handle.set_complete()
        except TimeoutError as e:
            handle.set_error(NavigationError(str(e), original_error=e))
        except Exception as e:
            handle.set_error(e)

    async def _progress_updater() -> None:
        last_log = 0.0
        while not handle.is_done():
            if handle.is_cancelled():
                return
            d = distance_fn(coordinates)
            if initial_dist > 0:
                p = 1.0 - (d / initial_dist)
                handle.set_progress(max(0.0, min(1.0, p)))
            now = time.monotonic()
            if now - last_log >= GOTO_NB_LOG_INTERVAL_S:
                logger.debug(
                    "%s: goto_coordinates (non-blocking) dist=%.1fm progress=%.0f%%",
                    log_prefix,
                    d,
                    handle.progress * 100,
                )
                last_log = now
            await asyncio.sleep(progress_poll_interval)

    t1 = asyncio.create_task(_wait_arrival())
    t2 = asyncio.create_task(_progress_updater())
    vehicle._command_tasks.extend([t1, t2])
    return handle


async def goto_offset(
    vehicle: Vehicle,
    north: float,
    east: float,
    down: float,
    *,
    tolerance: float,
    target_heading: float | None,
    timeout: float,
    blocking: bool,
) -> VehicleTask | None:
    """Navigate by NED offset; delegates to goto_coordinates."""
    target = vehicle.position + VectorNED(north, east, down)
    return await vehicle.goto_coordinates(
        target,
        tolerance=tolerance,
        target_heading=target_heading,
        timeout=timeout,
        blocking=blocking,
    )


async def goto_cardinal(
    vehicle: Vehicle,
    north: float,
    east: float,
    *,
    tolerance: float,
    target_heading: float | None,
    timeout: float,
    blocking: bool,
) -> VehicleTask | None:
    """Navigate by horizontal NED offset."""
    return await goto_offset(
        vehicle,
        north,
        east,
        0,
        tolerance=tolerance,
        target_heading=target_heading,
        timeout=timeout,
        blocking=blocking,
    )


async def goto_bearing_distance(
    vehicle: Vehicle,
    bearing_deg: float,
    distance_m: float,
    *,
    tolerance: float,
    target_heading: float | None,
    timeout: float,
    blocking: bool,
) -> VehicleTask | None:
    """Navigate along a bearing for a ground distance."""
    v = VectorNED(distance_m, 0, 0).rotate_by_angle(-bearing_deg)
    target = vehicle.position + v
    return await vehicle.goto_coordinates(
        target,
        tolerance=tolerance,
        target_heading=target_heading,
        timeout=timeout,
        blocking=blocking,
    )
