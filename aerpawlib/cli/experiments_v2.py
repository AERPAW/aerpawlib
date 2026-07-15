"""Run experimenter scripts using the v2 API."""

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
    DEFAULT_SAFETY_CHECKER_PORT,
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_NONE,
    VEHICLE_TYPE_ROVER,
)

from .disconnect import (
    await_disconnect_future,
    run_runner_with_disconnect_guard,
)
from .discovery import discover_runner

logger = logging.getLogger("aerpawlib")


def run_v2_experiment(
    args: Any,
    unknown_args: Any,
    experimenter_script: Any,
) -> None:
    """Run an experiment using the v2 API."""
    from aerpawlib.cli.progress_bar import update_progress

    update_progress("Loading API version: v2", completed=10)
    logger.debug("Loading API version: v2")
    start_time = time.time()
    try:
        api_module = importlib.import_module("aerpawlib.v2")
        logger.debug(f"Time to import API module: {time.time() - start_time:.2f}s")
    except Exception as e:
        logger.error(f"Failed to import aerpawlib.v2: {e}")
        sys.exit(1)

    runner, flag_zmq_runner = discover_runner(api_module, experimenter_script)
    assert runner is not None
    runner_instance = runner

    vehicle_type = {
        VEHICLE_TYPE_GENERIC: api_module.Vehicle,
        VEHICLE_TYPE_DRONE: api_module.Drone,
        VEHICLE_TYPE_ROVER: api_module.Rover,
        VEHICLE_TYPE_NONE: api_module.DummyVehicle,
    }.get(args.vehicle)

    if vehicle_type is None:
        logger.error(f"Invalid vehicle type: {args.vehicle}")
        raise Exception("Please specify a valid vehicle type")

    logger.info("Starting experiment execution (v2)")

    async def run_experiment_async() -> bool:
        """Connect, run the v2 runner, and perform shutdown/RTL cleanup."""
        no_aerpaw_env = getattr(args, "no_aerpaw_environment", False)

        if no_aerpaw_env:
            aerpaw_platform = None
            logger.info(
                "--no-aerpaw-environment set: skipping AERPAW platform connection, running in standalone mode.",
            )
        else:
            aerpaw_platform = api_module.AerpawPlatform(suppress_stdout=args.no_stdout)
            if not aerpaw_platform.is_connected:
                logger.critical(
                    "Failed to connect to AERPAW Environment. Because --no-aerpaw-environment was not passed, we are stopping. Pass --no-aerpaw-environment to run outside the AERPAW environment. If you are within the AERPAW environment, make sure the OEO Console is running.",
                )
                sys.exit(1)
            aerpaw_platform.log_to_oeo(
                "[aerpawlib] Starting experiment execution (v2)",
            )

        from aerpawlib.v2.safety import NoOpSafetyChecker, SafetyCheckerClient

        update_progress("Checking safety client...", completed=15)
        is_aerpaw = aerpaw_platform.is_connected if aerpaw_platform else False
        port_set = getattr(args, "safety_checker_port", None) is not None
        ip_set = getattr(args, "safety_checker_ip", None) is not None

        if not port_set and not ip_set and not is_aerpaw:
            safety_client = NoOpSafetyChecker(
                "Not in AERPAW environment and neither --safety-checker-port nor --safety-checker-ip was provided.",
            )
        else:
            effective_port = args.safety_checker_port if port_set else DEFAULT_SAFETY_CHECKER_PORT
            safety_addr = args.safety_checker_ip if ip_set else "127.0.0.1"
            try:
                client = SafetyCheckerClient(safety_addr, effective_port)
                ok, msg = await client.check_server_status()
                if ok:
                    safety_client = client
                else:
                    raise RuntimeError(msg or "SafetyCheckerServer check failed")
            except Exception as e:
                if is_aerpaw:
                    logger.critical(
                        "AERPAW environment requires SafetyCheckerServer. Connection to %s:%d failed: %s",
                        safety_addr,
                        effective_port,
                        e,
                    )
                    sys.exit(1)
                logger.error(
                    "SafetyCheckerServer connection failed (%s:%d): %s. Using passthrough (all validations pass).",
                    safety_addr,
                    effective_port,
                    e,
                )
                safety_client = NoOpSafetyChecker(
                    f"Connection to {safety_addr}:{effective_port} failed: {e}",
                )

        event_log = None
        structured_log_path = None
        if getattr(args, "structured_log", None):
            from aerpawlib.structured_log import StructuredEventLogger

            structured_log_path = Path(args.structured_log)
            if structured_log_path.exists():
                logger.warning(
                    "Structured log file %s already exists and will be overwritten",
                    str(structured_log_path),
                )
            event_log = StructuredEventLogger(structured_log_path.open("w"))

        update_progress("Connecting to vehicle...", completed=30)
        logger.info("Connecting to vehicle...")
        try:
            vehicle = await asyncio.wait_for(
                vehicle_type.connect(
                    args.conn,
                    args.mavsdk_port,
                    timeout=args.conn_timeout,
                    safety=safety_client,
                    aerpaw_platform=aerpaw_platform,
                ),
                timeout=args.conn_timeout,
            )
        except Exception as e:
            raise ConnectionError(f"Could not connect: {e}") from e

        shutdown_event = asyncio.Event()

        def handle_shutdown() -> None:
            """Initiate graceful shutdown from signal handlers or disconnects."""
            logger.warning("Initiating graceful shutdown...")
            shutdown_event.set()
            if vehicle and not vehicle.closed:
                with contextlib.suppress(RuntimeError):
                    asyncio.get_running_loop().create_task(vehicle.aclose())

        if event_log:
            assert structured_log_path is not None
            vehicle.set_event_log(event_log)
            runner_instance.set_event_log(event_log)
            logger.info(
                "Structured event logging -> %s",
                str(structured_log_path),
            )
            event_log.log_event("mission_start")

        def _on_disconnect() -> None:
            """Publish disconnect events to OEO and structured logs."""
            if aerpaw_platform:
                aerpaw_platform.log_to_oeo(
                    "[aerpawlib] Connection lost",
                    severity="CRITICAL",
                )
            if event_log:
                event_log.log_event("connection_lost")

        try:
            from aerpawlib.v2.safety.connection import setup_signal_handlers

            loop = asyncio.get_running_loop()
            disconnect_future = vehicle.watch_disconnect(
                args.heartbeat_timeout,
                on_disconnect=_on_disconnect,
            )
            setup_signal_handlers(
                loop,
                on_sigint=handle_shutdown,
                on_sigterm=handle_shutdown,
            )
        except (ImportError, NotImplementedError):
            disconnect_future = None
            signal.signal(signal.SIGINT, lambda s, f: handle_shutdown())
            signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown())

        runner_instance.initialize_args(unknown_args)

        shutdown_task = asyncio.create_task(shutdown_event.wait())

        success = False
        try:
            if args.initialize:
                update_progress("Initializing vehicle...", completed=50)
                preflight_coro = vehicle.initialize(args.initialize) if hasattr(vehicle, "initialize") else vehicle._preflight_wait(args.initialize)
                preflight_task = asyncio.create_task(preflight_coro)
                preflight_waits: list[asyncio.Task] = [
                    preflight_task,
                    shutdown_task,
                ]
                disconnect_guard_task = None
                if disconnect_future is not None:
                    disconnect_guard_task = asyncio.create_task(
                        await_disconnect_future(disconnect_future),
                    )
                    preflight_waits.append(disconnect_guard_task)
                # Race preflight against shutdown/disconnect so we do not keep
                # initializing after the mission is already terminating.
                done, _ = await asyncio.wait(
                    preflight_waits,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if preflight_task not in done:
                    preflight_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await preflight_task
                if shutdown_event.is_set():
                    return success
                if disconnect_guard_task is not None and disconnect_guard_task in done:
                    exc = disconnect_guard_task.exception()
                    if exc is not None:
                        raise exc

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
            run_task = asyncio.create_task(
                run_runner_with_disconnect_guard(
                    runner=runner_instance,
                    vehicle=vehicle,
                    disconnect_future=disconnect_future,
                ),
            )
            tasks = [run_task, shutdown_task]
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                if hasattr(t, "cancel"):
                    t.cancel()
            if shutdown_event.is_set():
                run_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await run_task
            else:
                await run_task
                success = True
        except Exception as e:
            logger.error(f"Experiment failed: {e}")
            traceback.print_exc()
        finally:
            if vehicle:
                heartbeat_lost = disconnect_future is not None and disconnect_future.done() and not disconnect_future.cancelled() and disconnect_future.exception() is not None
                if success and not vehicle.closed and vehicle.armed and args.rtl_at_end and not heartbeat_lost:
                    update_progress("Vehicle still armed! Returning home...", completed=90)
                    logger.warning("Vehicle still armed! Returning home...")
                    try:
                        if args.vehicle == VEHICLE_TYPE_DRONE:
                            await vehicle.return_to_launch()
                        elif args.vehicle == VEHICLE_TYPE_ROVER and vehicle.home_coords:
                            await vehicle.goto_coordinates(vehicle.home_coords)
                    except Exception as e:
                        logger.error(f"Return home failed: {e}")
                        traceback.print_exc()
                await vehicle.aclose()
            if safety_client is not None and hasattr(safety_client, "close"):
                try:
                    safety_client.close()
                except Exception as e:
                    logger.debug(f"Failed to close safety client cleanly: {e}")
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
        logger.error(f"Fatal error during v2 execution: {e}")
        traceback.print_exc()

    sys.exit(0 if experiment_success else 1)
