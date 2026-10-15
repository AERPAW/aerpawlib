"""Disconnect detection and runner racing for CLI experiments."""

from __future__ import annotations

import asyncio
import contextlib
import math
import time

from aerpawlib.cli.constants import RUNNER_DISCONNECT_POLL_INTERVAL_S


class VehicleClosedDuringMissionError(RuntimeError):
    """The disconnect watcher ended (vehicle closed / watcher cancelled) mid-mission."""


def validate_heartbeat_timeout(heartbeat_timeout: float) -> float:
    """Return ``heartbeat_timeout`` if it is finite and > 0, else raise ``ValueError``.

    ``0`` / negative values declare a healthy link dead; ``nan`` / ``inf``
    silently disable disconnect detection.
    """
    try:
        value = float(heartbeat_timeout)
    except (TypeError, ValueError) as e:
        raise ValueError(f"heartbeat timeout must be a number, got {heartbeat_timeout!r}") from e
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"heartbeat timeout must be finite and > 0, got {heartbeat_timeout!r}")
    return value


def build_connection_loss_error(
    heartbeat_error_cls,
    age: float,
    message: str,
    original_error: Exception | None = None,
) -> Exception:
    """Build a connection-loss exception for both v1 and v2 constructors.

    Args:
        heartbeat_error_cls: Exception class to instantiate.
        age: Seconds since disconnection started.
        message: Human-readable error text.
        original_error: Optional root cause from lower layers.

    Returns:
        Exception: Instantiated connection-loss exception.
    """
    kwargs: dict[str, object] = {
        "last_heartbeat_age": age,
        "message": message,
    }
    if original_error is not None:
        kwargs["original_error"] = original_error
    try:
        return heartbeat_error_cls(**kwargs)
    except TypeError:
        try:
            return heartbeat_error_cls(message=message)
        except TypeError:
            return heartbeat_error_cls()


async def wait_for_v1_connection_loss(
    vehicle,
    heartbeat_timeout: float,
    heartbeat_error_cls,
):
    """Wait until v1 connection is lost long enough to be considered fatal.

    Args:
        vehicle: v1 vehicle instance.
        heartbeat_timeout: Allowed seconds of disconnection before failure.
        heartbeat_error_cls: Exception class raised on disconnect.

    Raises:
        Exception: A heartbeat/connection loss exception.
    """
    disconnected_since = None
    timeout_s = validate_heartbeat_timeout(heartbeat_timeout)
    while not getattr(vehicle, "closed", getattr(vehicle, "_closed", False)):
        connection_error = getattr(vehicle, "_connection_error", None)
        if connection_error is not None:
            raise build_connection_loss_error(
                heartbeat_error_cls,
                age=0.0,
                message=f"Vehicle connection lost ({connection_error})",
                original_error=connection_error,
            )

        if bool(getattr(vehicle, "connected", True)):
            disconnected_since = None
        else:
            if disconnected_since is None:
                disconnected_since = time.monotonic()
            age = time.monotonic() - disconnected_since
            if age >= timeout_s:
                raise build_connection_loss_error(
                    heartbeat_error_cls,
                    age=age,
                    message=f"Vehicle connection lost (disconnected for {age:.1f}s)",
                )
        await asyncio.sleep(RUNNER_DISCONNECT_POLL_INTERVAL_S)


async def run_runner_with_disconnect_guard(
    runner,
    vehicle,
    disconnect_future=None,
):
    """Run ``runner.run(vehicle)`` and race against disconnect/shutdown future.

    Args:
        runner: Runner instance to execute.
        vehicle: Vehicle passed into ``runner.run``.
        disconnect_future: Optional future that raises on connection loss.
    """
    run_task = asyncio.create_task(runner.run(vehicle))
    try:
        if disconnect_future is None:
            await run_task
            return

        done, pending = await asyncio.wait(
            [run_task, disconnect_future],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if disconnect_future in done:
            run_finished_ok = run_task in done and not run_task.cancelled() and run_task.exception() is None
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run_task
            exc = None if disconnect_future.cancelled() else disconnect_future.exception()
            if exc is not None:
                raise exc
            if run_finished_ok:
                return
            # The watcher only returns normally when the vehicle was closed (or
            # it was cancelled). The mission did not finish: that is a failure,
            # not a success that would make end-of-mission RTL eligible.
            raise VehicleClosedDuringMissionError(
                "Vehicle connection closed while the mission was still running",
            )

        for task in pending:
            if hasattr(task, "cancel"):
                task.cancel()
        await run_task
    finally:
        # Cancelling this wrapper (SIGINT/SIGTERM) does not cancel run_task by
        # itself; stop the runner (and let its cleanup run) before the caller
        # closes the vehicle or decides on RTL.
        if not run_task.done():
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await run_task


async def await_disconnect_future(disconnect_future) -> None:
    """Await a disconnect future so it can be raced as a task.

    Args:
        disconnect_future: Future that completes when connection is lost.
    """
    await disconnect_future
