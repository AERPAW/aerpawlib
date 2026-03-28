"""Disconnect detection and runner racing for CLI experiments."""

import asyncio
import time
from typing import Optional

from aerpawlib.cli.constants import (
    RUNNER_DISCONNECT_POLL_INTERVAL_S,
    VEHICLE_ATTR_CLOSED,
    VEHICLE_ATTR_CONNECTION_ERROR,
    VEHICLE_ATTR_CONNECTED,
    VEHICLE_CONNECTION_LOST_MSG_WITH_ERROR_FMT,
    VEHICLE_CONNECTION_LOST_MSG_WITH_DURATION_FMT,
)


def build_connection_loss_error(
    heartbeat_error_cls,
    age: float,
    message: str,
    original_error: Optional[Exception] = None,
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
    timeout_s = max(heartbeat_timeout, 0.0)
    while not getattr(vehicle, VEHICLE_ATTR_CLOSED, False):
        connection_error = getattr(vehicle, VEHICLE_ATTR_CONNECTION_ERROR, None)
        if connection_error is not None:
            raise build_connection_loss_error(
                heartbeat_error_cls,
                age=0.0,
                message=VEHICLE_CONNECTION_LOST_MSG_WITH_ERROR_FMT.format(
                    connection_error=connection_error
                ),
                original_error=connection_error,
            )

        if bool(getattr(vehicle, VEHICLE_ATTR_CONNECTED, True)):
            disconnected_since = None
        else:
            if disconnected_since is None:
                disconnected_since = time.monotonic()
            age = time.monotonic() - disconnected_since
            if age >= timeout_s:
                raise build_connection_loss_error(
                    heartbeat_error_cls,
                    age=age,
                    message=VEHICLE_CONNECTION_LOST_MSG_WITH_DURATION_FMT.format(
                        age=age
                    ),
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
    if disconnect_future is None:
        await run_task
        return

    done, pending = await asyncio.wait(
        [run_task, disconnect_future],
        return_when=asyncio.FIRST_COMPLETED,
    )
    if disconnect_future in done:
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass
        exc = None if disconnect_future.cancelled() else disconnect_future.exception()
        if exc is not None:
            raise exc
        return

    for task in pending:
        if hasattr(task, "cancel"):
            task.cancel()
    await run_task


async def await_disconnect_future(disconnect_future) -> None:
    """Await a disconnect future so it can be raced as a task.

    Args:
        disconnect_future: Future that completes when connection is lost.
    """
    await disconnect_future
