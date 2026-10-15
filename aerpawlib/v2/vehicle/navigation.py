"""Shared navigation helpers for v2 Drone and Rover (internal)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from aerpawlib.v2.constants import (
    GOTO_LOG_INTERVAL_S,
    GOTO_NB_LOG_INTERVAL_S,
    HEARTBEAT_TIMEOUT_S,
    POLLING_DELAY_S,
)
from aerpawlib.v2.exceptions import NavigationError
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.types import Coordinate, VectorNED

from .task import VehicleTask

if TYPE_CHECKING:
    from .base import Vehicle

logger = get_logger(LogComponent.VEHICLE)

# Arrival needs this many consecutive in-tolerance position samples, so one
# sample taken while passing through the bubble does not count as arrived.
ARRIVAL_CONSECUTIVE_SAMPLES = 2
# Arrival fails once the newest position sample is older than this.
ARRIVAL_MAX_TELEMETRY_AGE_S = HEARTBEAT_TIMEOUT_S


def _arrival_link_problem(vehicle: Vehicle) -> str | None:
    """Return why arrival cannot be trusted (link down / stale fix), or None."""
    if not vehicle.link_alive:
        return "vehicle link is down"
    age = time.monotonic() - vehicle._connection.last_telemetry_at
    if age > ARRIVAL_MAX_TELEMETRY_AGE_S:
        return f"position telemetry is stale ({age:.1f}s old)"
    return None


class _ArrivalTracker:
    """Count consecutive fresh position samples that satisfy done_moving()."""

    def __init__(self, vehicle: Vehicle) -> None:
        self._vehicle = vehicle
        self._hits = 0
        self._last_seq: int | None = None

    def arrived(self) -> bool:
        if not self._vehicle.done_moving():
            self._hits = 0
            self._last_seq = None
            return False
        seq = self._vehicle._state.position_seq
        if seq != self._last_seq:
            self._hits += 1
            self._last_seq = seq
        return self._hits >= ARRIVAL_CONSECUTIVE_SAMPLES


async def wait_for_blocking_goto(
    vehicle: Vehicle,
    coordinates: Coordinate,
    *,
    distance_fn: Callable[[], float],
    tolerance: float,
    timeout: float,
    log_prefix: str,
    generation: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    """Poll until the vehicle arrives at ``coordinates`` (or ``should_stop()``).

    Raises:
        NavigationError: On timeout, link loss / stale telemetry, or when a
            newer movement command superseded this one (``generation``).
    """
    start = time.monotonic()
    last_log = 0.0
    tracker = _ArrivalTracker(vehicle)
    while True:
        if should_stop is not None and should_stop():
            return
        if generation is not None and vehicle._move_generation != generation:
            raise NavigationError("superseded by a newer movement command")
        problem = _arrival_link_problem(vehicle)
        if problem is not None:
            raise NavigationError(f"{log_prefix}: cannot confirm arrival: {problem}")
        if tracker.arrived():
            return
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise NavigationError(f"{log_prefix} goto timed out within {timeout}s")
        now = time.monotonic()
        if now - last_log >= GOTO_LOG_INTERVAL_S:
            dist = distance_fn()
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
    generation: int | None = None,
) -> VehicleTask:
    """Return a VehicleTask tracking non-blocking goto progress."""
    handle = VehicleTask()
    logger.debug("%s: goto_coordinates returning non-blocking VehicleTask", log_prefix)
    handle.set_on_cancel(on_cancel)

    initial_dist = distance_fn()

    async def _wait_arrival() -> None:
        try:
            await wait_for_blocking_goto(
                vehicle,
                coordinates,
                distance_fn=distance_fn,
                tolerance=tolerance,
                timeout=timeout,
                log_prefix=log_prefix,
                generation=generation,
                should_stop=handle.is_cancelled,
            )
            if handle.is_cancelled():
                handle.set_complete()
                return
            if on_complete is not None:
                on_complete()
            handle.set_progress(1.0)
            handle.set_complete()
        except Exception as e:
            if handle.is_cancelled():
                handle.set_complete()
                return
            if generation is not None:
                vehicle._release_move_gate(generation)
            handle.set_error(e)

    async def _progress_updater() -> None:
        last_log = 0.0
        while not handle.is_done():
            if handle.is_cancelled():
                return
            d = distance_fn()
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
