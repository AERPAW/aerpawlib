"""Run experimenter scripts using the v2 API."""

import asyncio
import contextlib
import logging
import os
import signal
import sys
import traceback
from typing import Any

from aerpawlib.cli.constants import (
    API_CLASS_AERPAW_PLATFORM,
    API_CLASS_DRONE,
    API_CLASS_DUMMY_VEHICLE,
    API_CLASS_ROVER,
    API_CLASS_VEHICLE,
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
    api_module: Any,
    experimenter_script: Any,
    start_time: Any = None,
) -> None:
    """Run an experiment using the v2 API."""
    runner, flag_zmq_runner = discover_runner(api_module, experimenter_script)
    assert runner is not None
    runner_instance = runner

    Vehicle = getattr(api_module, API_CLASS_VEHICLE)
    Drone = getattr(api_module, API_CLASS_DRONE)
    Rover = getattr(api_module, API_CLASS_ROVER)
    DummyVehicle = getattr(api_module, API_CLASS_DUMMY_VEHICLE, None)
    AERPAW_Platform = getattr(api_module, API_CLASS_AERPAW_PLATFORM, None)

    vehicle_type = {
        VEHICLE_TYPE_GENERIC: Vehicle,
        VEHICLE_TYPE_DRONE: Drone,
        VEHICLE_TYPE_ROVER: Rover,
        VEHICLE_TYPE_NONE: DummyVehicle,
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
                "--no-aerpaw-environment set: skipping AERPAW platform connection, "
                "running in standalone mode.",
            )
        elif AERPAW_Platform:
            aerpaw_platform = AERPAW_Platform()
            aerpaw_platform.set_no_stdout(args.no_stdout)
            if not aerpaw_platform._connected:
                logger.critical(
                    "It seems like we're in standalone mode but "
                    "--no-aerpaw-environment was not passed. "
                    "Pass --no-aerpaw-environment to run outside the AERPAW "
                    "environment.",
                )
                sys.exit(1)
        else:
            aerpaw_platform = None

        from aerpawlib.v2.safety import NoOpSafetyChecker, SafetyCheckerClient

        is_aerpaw = aerpaw_platform._connected if aerpaw_platform else False
        effective_port = (
            args.safety_checker_port
            if args.safety_checker_port is not None
            else (DEFAULT_SAFETY_CHECKER_PORT if is_aerpaw else None)
        )
        if effective_port is None:
            safety_client = NoOpSafetyChecker(
                "Not in AERPAW environment and --safety-checker-port not provided.",
            )
        else:
            safety_addr = "127.0.0.1"
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
                        "AERPAW environment requires SafetyCheckerServer. "
                        "Connection to %s:%d failed: %s",
                        safety_addr,
                        effective_port,
                        e,
                    )
                    sys.exit(1)
                logger.error(
                    "SafetyCheckerServer connection failed (%s:%d): %s. Using "
                    "passthrough (all validations pass).",
                    safety_addr,
                    effective_port,
                    e,
                )
                safety_client = NoOpSafetyChecker(
                    f"Connection to {safety_addr}:{effective_port} failed: {e}",
                )

        event_log = None
        if getattr(args, "structured_log", None):
            from aerpawlib.structured_log import StructuredEventLogger

            if os.path.exists(args.structured_log):
                logger.warning(
                    "Structured log file %s already exists and will be overwritten",
                    args.structured_log,
                )
            event_log = StructuredEventLogger(open(args.structured_log, "w"))

        logger.info("Connecting to vehicle...")
        try:
            vehicle = await asyncio.wait_for(
                vehicle_type.connect(
                    args.conn,
                    args.mavsdk_port,
                    timeout=args.conn_timeout,
                    safety=safety_client,
                ),
                timeout=args.conn_timeout,
            )
        except Exception as e:
            raise ConnectionError(f"Could not connect: {e}")

        shutdown_event = asyncio.Event()
        _conn_handler_ref: list = [None]

        def handle_shutdown() -> None:
            """Initiate graceful shutdown from signal handlers or disconnects."""
            logger.warning("Initiating graceful shutdown...")
            shutdown_event.set()
            if _conn_handler_ref[0] is not None:
                _conn_handler_ref[0].stop()
            if vehicle:
                vehicle.close()

        if event_log:
            vehicle.set_event_log(event_log)
            runner_instance.set_event_log(event_log)
            logger.info("Structured event logging -> %s", args.structured_log)
            event_log.log_event("mission_start")

        def _on_disconnect() -> None:
            """Publish disconnect events to OEO and structured logs."""
            if aerpaw_platform:
                aerpaw_platform.log_to_oeo(
                    "[aerpawlib] Connection lost", severity="CRITICAL",
                )
            if event_log:
                event_log.log_event("connection_lost")

        try:
            from aerpawlib.v2.safety.connection import (
                ConnectionHandler,
                setup_signal_handlers,
            )

            loop = asyncio.get_running_loop()
            conn_handler = ConnectionHandler(
                vehicle,
                heartbeat_timeout=args.heartbeat_timeout,
                on_disconnect=_on_disconnect,
            )
            _conn_handler_ref[0] = conn_handler
            vehicle.set_heartbeat_tick_callback(conn_handler.heartbeat_tick)
            conn_handler.start()
            disconnect_future = conn_handler.get_disconnect_future()
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
            if args.initialize and hasattr(vehicle, "_preflight_wait"):
                preflight_task = asyncio.create_task(
                    vehicle._preflight_wait(args.initialize),
                )
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
                if not args.zmq_identifier or not args.zmq_server_addr:
                    logger.error(
                        "ZMQ runner requires --zmq-identifier and --zmq-proxy-server. "
                        "Example: --zmq-identifier leader --zmq-proxy-server 127.0.0.1",
                    )
                    raise ValueError(
                        "ZMQ runners require --zmq-identifier and --zmq-proxy-server",
                    )
                runner_instance._initialize_zmq_bindings(
                    args.zmq_identifier, args.zmq_server_addr,
                )

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
                heartbeat_lost = (
                    disconnect_future is not None
                    and disconnect_future.done()
                    and not disconnect_future.cancelled()
                    and disconnect_future.exception() is not None
                )
                if (
                    not vehicle.closed
                    and vehicle.armed
                    and args.rtl_at_end
                    and not heartbeat_lost
                ):
                    logger.warning("Vehicle still armed! RTLing...")
                    try:
                        if args.vehicle == VEHICLE_TYPE_DRONE:
                            await vehicle.return_to_launch()
                        elif args.vehicle == VEHICLE_TYPE_ROVER and vehicle.home_coords:
                            await vehicle.goto_coordinates(vehicle.home_coords)
                    except Exception as e:
                        logger.error(f"RTL failed: {e}")
                        traceback.print_exc()
                vehicle.close()
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
        return success

    experiment_success = False
    try:
        experiment_success = asyncio.run(run_experiment_async())
    except Exception as e:
        logger.error(f"Fatal error during v2 execution: {e}")
        traceback.print_exc()

    sys.exit(0 if experiment_success else 1)
