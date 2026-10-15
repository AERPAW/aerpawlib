"""Run experimenter scripts using the v1 API."""

import asyncio
import contextlib
import importlib
import logging
import signal
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from aerpawlib.cli.constants import (
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_NONE,
    VEHICLE_TYPE_ROVER,
)
from aerpawlib.cli.safety import resolve_safety_checker_target

from .disconnect import (
    run_runner_with_disconnect_guard,
    wait_for_v1_connection_loss,
)
from .discovery import discover_runner, initialize_script_args
from .process_guard import (
    ShutdownSignalHandler,
    install_mavsdk_server_tracking,
    kill_mavsdk_servers,
    mavsdk_server_mark,
)
from .rtl import return_home_if_armed

logger = logging.getLogger("aerpawlib")


async def run_blocking_until_shutdown(
    func: Any,
    shutdown_event: asyncio.Event,
    *args: Any,
) -> bool:
    """Run blocking ``func(*args)`` in a daemon thread, racing ``shutdown_event``.

    v1 preflight (``Vehicle.initialize`` / ``_preflight_wait``) is a
    ``time.sleep`` loop of up to ``ARMABLE_TIMEOUT_S``. Running it on the event
    loop hides SIGINT/SIGTERM until it returns. A daemon thread does not keep
    the process alive (or ``asyncio.run`` waiting) after shutdown.

    Returns:
        True if ``func`` finished, False if shutdown was requested first.

    Raises:
        Exception: Whatever ``func`` raised.
    """
    import threading

    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()

    def _finish(exc: BaseException | None) -> None:
        if done.done():
            return
        if exc is None:
            done.set_result(None)
        else:
            done.set_exception(exc)

    def _worker() -> None:
        try:
            func(*args)
        except BaseException as e:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_finish, e)
        else:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_finish, None)

    threading.Thread(target=_worker, name="aerpawlib-v1-preflight", daemon=True).start()
    shutdown_task = asyncio.ensure_future(shutdown_event.wait())
    try:
        await asyncio.wait({done, shutdown_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        if not shutdown_task.done():
            shutdown_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await shutdown_task
    if done.done():
        done.result()
        return True
    # Retrieve a late exception so it is not reported as "never retrieved".
    done.add_done_callback(lambda f: f.cancelled() or f.exception())
    return False


def run_v1_experiment(
    args: Any,
    unknown_args: Any,
    experimenter_script: Any,
) -> None:
    """Run an experiment using the v1 API."""
    from aerpawlib.cli.progress_bar import update_progress

    update_progress("Loading API version: v1", completed=10)
    logger.debug("Loading API version: v1")
    start_time = time.time()
    try:
        api_module = importlib.import_module("aerpawlib.v1")
        logger.debug(f"Time to import API module: {time.time() - start_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to import aerpawlib.v1: {e}")
        sys.exit(1)

    runner, flag_zmq_runner = discover_runner(api_module, experimenter_script)
    assert runner is not None
    runner_instance = runner
    # Parse script arguments before connecting: an argparse error or
    # ``-- --help`` exits here without leaving a vehicle or server open.
    initialize_script_args(runner_instance, unknown_args)

    vehicle_type = {
        VEHICLE_TYPE_GENERIC: api_module.Vehicle,
        VEHICLE_TYPE_DRONE: api_module.Drone,
        VEHICLE_TYPE_ROVER: api_module.Rover,
        VEHICLE_TYPE_NONE: api_module.DummyVehicle,
    }.get(args.vehicle)
    aerpaw_platform_cls = api_module.AERPAW_Platform

    if vehicle_type is None:
        logger.error(f"Invalid vehicle type: {args.vehicle}")
        raise Exception("Please specify a valid vehicle type")

    logger.info("Starting experiment execution (v1)")

    async def run_experiment_async() -> bool:
        """Connect the vehicle, run the mission, and handle cleanup/RTL."""
        from aerpawlib.cli.progress_bar import update_progress

        update_progress("Connecting to vehicle...", completed=20)
        logger.info("Connecting to vehicle...")
        install_mavsdk_server_tracking()
        server_mark = mavsdk_server_mark()
        try:
            # v1 Vehicle.__init__ blocks until connected or raises on failure
            vehicle = await asyncio.wait_for(
                # linter has no idea what is going on here
                asyncio.to_thread(vehicle_type, args.conn, args.mavsdk_port),
                timeout=args.conn_timeout,
            )
        except BaseException as e:
            # The connect thread cannot be cancelled; kill its server (and any
            # it starts later) so neither the port nor the process is held.
            kill_mavsdk_servers(server_mark, reject_new=True)
            if not isinstance(e, Exception):
                raise
            raise ConnectionError(f"Could not connect: {e}") from e

        # Everything after connect (including sys.exit on AERPAW / safety
        # checker failures) must close the vehicle.
        try:
            return await _run_connected(vehicle)
        finally:
            with contextlib.suppress(Exception):
                vehicle.close()

    async def _run_connected(vehicle: Any) -> bool:
        """Set up logging/safety, run the mission, and handle cleanup/RTL."""
        event_log = None
        if getattr(args, "structured_log", None):
            from aerpawlib.structured_log import StructuredEventLogger

            path = Path(args.structured_log)
            if path.exists():
                logger.warning(
                    "Structured log file %s already exists and will be overwritten",
                    str(path),
                )
            event_log = StructuredEventLogger(path.open("w"))
            vehicle.set_event_log(event_log)
            event_log.log_event("mission_start")
            logger.info("Structured event logging -> %s", str(path))

        shutdown_event = asyncio.Event()

        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            """Set the shutdown event on the loop thread (signal-safe)."""
            if not shutdown_event.is_set():
                shutdown_event.set()

        def handle_shutdown() -> None:
            """Request graceful shutdown from SIGINT/SIGTERM."""
            logger.warning("Initiating graceful shutdown... (send the signal again to force exit)")
            loop.call_soon_threadsafe(request_shutdown)

        signal_handler = ShutdownSignalHandler(handle_shutdown)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        no_aerpaw_env = getattr(args, "no_aerpaw_environment", False)
        if no_aerpaw_env:
            logger.info(
                "--no-aerpaw-environment set: skipping AERPAW platform connection, running in standalone mode.",
            )
            # Writing to the lazy AERPAW_Platform proxy constructs it, which
            # pings the OEO forwarder; only do that when muting was requested.
            if aerpaw_platform_cls and args.no_stdout:
                aerpaw_platform_cls._no_stdout = args.no_stdout
        elif aerpaw_platform_cls:
            aerpaw_platform_cls._no_stdout = args.no_stdout
            if not aerpaw_platform_cls._connected:
                logger.critical(
                    "Failed to connect to AERPAW Environment. Because --no-aerpaw-environment was not passed, we are stopping. Pass --no-aerpaw-environment to run outside the AERPAW environment. If you are within the AERPAW environment, make sure the OEO Console is running.",
                )
                sys.exit(1)
            try:
                aerpaw_platform_cls.log_to_oeo(
                    "[aerpawlib] Starting experiment execution (v1)",
                )
            except Exception as e:
                logger.debug(f"Failed to log start to OEO: {e}")

        # Check the flag first: reading ``_connected`` constructs the lazy
        # AERPAW_Platform singleton, which pings the OEO forwarder.
        is_aerpaw = bool(not no_aerpaw_env and aerpaw_platform_cls and aerpaw_platform_cls._connected)
        safety_target = resolve_safety_checker_target(
            ip=getattr(args, "safety_checker_ip", None),
            port=getattr(args, "safety_checker_port", None),
            extra_args=unknown_args,
            is_aerpaw=is_aerpaw,
        )
        if safety_target is not None:
            from aerpawlib.v1.safety import SafetyCheckerClient

            safety_addr, effective_port = safety_target
            try:
                client = SafetyCheckerClient(safety_addr, effective_port)
                ok, msg = client.check_server_status()
                if not ok:
                    raise RuntimeError(msg or "SafetyCheckerServer check failed")
                vehicle.safety = client
                logger.info("v1 SafetyCheckerClient attached at %s:%s", safety_addr, effective_port)
            except Exception as e:
                if is_aerpaw:
                    logger.critical(
                        "AERPAW environment requires SafetyCheckerServer. Connection to %s:%s failed: %s",
                        safety_addr,
                        effective_port,
                        e,
                    )
                    sys.exit(1)
                logger.error(
                    "SafetyCheckerServer connection failed (%s:%s): %s. Commands will not be geofence-checked.",
                    safety_addr,
                    effective_port,
                    e,
                )

        success = False
        heartbeat_lost = False
        heartbeat_error_cls = api_module.HeartbeatLostError
        disconnect_task = None
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        try:
            if args.initialize:
                update_progress("Initializing vehicle...", completed=50)
                preflight = getattr(vehicle, "initialize", None) or getattr(vehicle, "_preflight_wait", None)
                if preflight is not None:
                    await run_blocking_until_shutdown(preflight, shutdown_event, args.initialize)
            if shutdown_event.is_set():
                return success

            if flag_zmq_runner:
                if not args.zmq_identifier or not args.zmq_proxy_server:
                    logger.error(
                        "ZMQ runner requires --zmq-identifier and --zmq-proxy-server. Example: --zmq-identifier leader --zmq-proxy-server 127.0.0.1",
                    )
                    raise ValueError(
                        "ZMQ runners require --zmq-identifier and --zmq-proxy-server",
                    )
                runner_instance._initialize_zmq_bindings(
                    args.zmq_identifier,
                    args.zmq_proxy_server,
                )

            update_progress("Running experiment...", completed=60)
            disconnect_task = asyncio.create_task(
                wait_for_v1_connection_loss(
                    vehicle=vehicle,
                    heartbeat_timeout=args.heartbeat_timeout,
                    heartbeat_error_cls=heartbeat_error_cls,
                ),
            )
            run_task = asyncio.create_task(
                run_runner_with_disconnect_guard(
                    runner=runner_instance,
                    vehicle=vehicle,
                    disconnect_future=disconnect_task,
                ),
            )
            _done, pending = await asyncio.wait(
                [run_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if shutdown_event.is_set():
                run_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await run_task
            else:
                await run_task
                success = True
        except Exception as exc:
            heartbeat_lost = isinstance(exc, heartbeat_error_cls)
            if heartbeat_lost and aerpaw_platform_cls and not no_aerpaw_env:
                try:
                    aerpaw_platform_cls.log_to_oeo(
                        "[aerpawlib] Connection lost",
                        severity="CRITICAL",
                    )
                except Exception as e:
                    logger.debug(f"Failed to log connection loss to OEO: {e}")
            logger.error(f"Experiment failed: {exc}")
            traceback.print_exc()
        finally:
            if not shutdown_task.done():
                shutdown_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await shutdown_task
            if disconnect_task is not None and not disconnect_task.done():
                disconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await disconnect_task
            if vehicle:
                if success:
                    await return_home_if_armed(
                        vehicle,
                        args.vehicle,
                        args.rtl_at_end,
                        reason="experiment ending",
                    )
                vehicle.close()
            if event_log is not None:
                with contextlib.suppress(Exception):
                    event_log.log_event("mission_end", success=success)
                try:
                    event_log.close()
                except Exception as e:
                    logger.debug(f"Failed to close structured event log: {e}")
            update_progress("Experiment completed!", completed=100)
        return success

    experiment_success = False
    try:
        experiment_success = asyncio.run(run_experiment_async())
    except Exception as e:
        logger.error(f"Fatal error during v1 execution: {e}")
        traceback.print_exc()
    finally:
        # The vehicle normally stops its own server; this catches any left over
        # so the process can exit and the gRPC port is freed.
        kill_mavsdk_servers(reject_new=True)

    sys.exit(0 if experiment_success else 1)
