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
    FILTER_REASON_ATTEMPTS,
    FILTER_REASON_RETRY_S,
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_NONE,
    VEHICLE_TYPE_ROVER,
)
from aerpawlib.cli.safety import resolve_safety_checker_target

from .disconnect import (
    await_disconnect_future,
    run_runner_with_disconnect_guard,
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
    # Parse script arguments before anything is connected: an argparse error
    # or ``-- --help`` exits here without leaving a vehicle or server open.
    initialize_script_args(runner_instance, unknown_args)

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
            from aerpawlib._internal.aerpaw_ping import (
                aerpaw_env_vars_present,
                ping_forward_server,
            )
            from aerpawlib.v2.constants import (
                AERPAW_PING_TIMEOUT_S,
                DEFAULT_FORWARD_SERVER_IP,
                DEFAULT_FORWARD_SERVER_PORT,
            )

            if aerpaw_env_vars_present() and ping_forward_server(
                DEFAULT_FORWARD_SERVER_IP,
                DEFAULT_FORWARD_SERVER_PORT,
                AERPAW_PING_TIMEOUT_S,
            ):
                logger.critical(
                    f"--no-aerpaw-environment is SITL-only, but the AERPAW OEO forwarder at {DEFAULT_FORWARD_SERVER_IP}:{DEFAULT_FORWARD_SERVER_PORT} answered ping. Refusing to start: this flag would skip AERPAW detection and can send action.hold() (LOITER), which severs the E-VM MAVLink link.",
                )
                sys.exit(1)
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
        safety_target = resolve_safety_checker_target(
            ip=getattr(args, "safety_checker_ip", None),
            port=getattr(args, "safety_checker_port", None),
            extra_args=unknown_args,
            is_aerpaw=is_aerpaw,
        )

        if safety_target is None:
            safety_client = NoOpSafetyChecker(
                "Not in AERPAW environment and neither --safety-checker-port nor --safety-checker-ip was provided.",
            )
        else:
            safety_addr, effective_port = safety_target
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
        install_mavsdk_server_tracking()
        server_mark = mavsdk_server_mark()
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
        except BaseException as e:
            # Connect owns the mavsdk_server it started; on failure nothing
            # else will stop it (the traceback keeps the System alive).
            kill_mavsdk_servers(server_mark, reject_new=True)
            if safety_client is not None and hasattr(safety_client, "close"):
                with contextlib.suppress(Exception):
                    safety_client.close()
            if event_log is not None:
                with contextlib.suppress(Exception):
                    event_log.close()
            if not isinstance(e, Exception):
                raise
            raise ConnectionError(f"Could not connect: {e}") from e

        shutdown_event = asyncio.Event()

        def handle_shutdown() -> None:
            """Request graceful shutdown from SIGINT/SIGTERM."""
            logger.warning("Initiating graceful shutdown... (send the signal again to force exit)")
            shutdown_event.set()

        signal_handler = ShutdownSignalHandler(handle_shutdown)

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
                    severity=api_module.OeoSeverity.CRITICAL,
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
                on_sigint=signal_handler.for_signal(signal.SIGINT),
                on_sigterm=signal_handler.for_signal(signal.SIGTERM),
            )
        except (ImportError, NotImplementedError):
            disconnect_future = None
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

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
                if preflight_task in done and not preflight_task.cancelled():
                    preflight_exc = preflight_task.exception()
                    if preflight_exc is not None:
                        # Never fly a mission whose preflight failed.
                        raise preflight_exc
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
            reason = None if vehicle is None or isinstance(e, api_module.FilterAbortedError) else await _filter_abort_reason(vehicle)
            if reason is not None:
                # A command usually fails on the dead link before the disconnect watch asks.
                logger.error(f"Experiment failed: {api_module.FilterAbortedError(reason)}")
            logger.error(f"Experiment failed: {e}")
            traceback.print_exc()
        finally:
            if vehicle:
                if success:
                    await return_home_if_armed(
                        vehicle,
                        args.vehicle,
                        args.rtl_at_end,
                        reason="experiment ending",
                    )
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

    async def _filter_abort_reason(vehicle: Any) -> str | None:
        """Why the C-VM filter cut the link, if that is why the mission failed."""
        for attempt in range(FILTER_REASON_ATTEMPTS):
            try:
                reason = await vehicle.filter_abort_reason()
            except Exception as e:
                logger.debug(f"Could not ask the safety checker why the link is down: {e}")
                return None
            if reason is not None or vehicle.connected:
                return reason
            if attempt + 1 < FILTER_REASON_ATTEMPTS:
                await asyncio.sleep(FILTER_REASON_RETRY_S)
        return None

    experiment_success = False
    try:
        experiment_success = asyncio.run(run_experiment_async())
    except Exception as e:
        logger.error(f"Fatal error during v2 execution: {e}")
        traceback.print_exc()
    finally:
        # The vehicle normally stops its own server; this catches any left over
        # so the process can exit and the gRPC port is freed.
        kill_mavsdk_servers(reject_new=True)

    sys.exit(0 if experiment_success else 1)
