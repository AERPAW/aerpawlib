"""Run experimenter scripts using the v1 API."""

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
    API_CLASS_HEARTBEAT_LOST_ERROR,
    API_CLASS_ROVER,
    API_CLASS_VEHICLE,
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_NONE,
    VEHICLE_TYPE_ROVER,
)

from .disconnect import (
    run_runner_with_disconnect_guard,
    wait_for_v1_connection_loss,
)
from .discovery import discover_runner

logger = logging.getLogger("aerpawlib")


def run_v1_experiment(
    args: Any,
    unknown_args: Any,
    api_module: Any,
    experimenter_script: Any,
    version_name: str = "v1",
) -> None:
    """Run an experiment using the v1 API."""
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

    logger.info(f"Starting experiment execution ({version_name})")

    async def run_experiment_async() -> bool:
        """Connect the vehicle, run the mission, and handle cleanup/RTL."""
        event_log = None
        logger.info("Connecting to vehicle...")
        try:
            # v1 Vehicle.__init__ blocks until connected or raises; no async _connected
            # poll.
            vehicle = await asyncio.wait_for(
                asyncio.to_thread(vehicle_type, args.conn, args.mavsdk_port),
                timeout=args.conn_timeout,
            )
        except Exception as e:
            raise ConnectionError(f"Could not connect: {e}")

        if getattr(args, "structured_log", None):
            from aerpawlib.structured_log import StructuredEventLogger

            if os.path.exists(args.structured_log):
                logger.warning(
                    "Structured log file %s already exists and will be overwritten",
                    args.structured_log,
                )
            event_log = StructuredEventLogger(open(args.structured_log, "w"))
            vehicle.set_event_log(event_log)
            event_log.log_event("mission_start")
            logger.info("Structured event logging -> %s", args.structured_log)

        def handle_shutdown(signum: Any, frame: Any) -> None:
            """Handle SIGINT/SIGTERM by closing the vehicle then exiting."""
            logger.warning("Initiating graceful shutdown...")
            if vehicle:
                vehicle.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        no_aerpaw_env = getattr(args, "no_aerpaw_environment", False)
        if no_aerpaw_env:
            logger.info(
                "--no-aerpaw-environment set: skipping AERPAW platform connection, "
                "running in standalone mode.",
            )
            if AERPAW_Platform:
                AERPAW_Platform._no_stdout = args.no_stdout
        elif AERPAW_Platform:
            AERPAW_Platform._no_stdout = args.no_stdout
            if not AERPAW_Platform._connected:
                logger.critical(
                    "It seems like we're in standalone mode but "
                    "--no-aerpaw-environment was not passed. "
                    "Pass --no-aerpaw-environment to run outside the AERPAW "
                    "environment.",
                )
                sys.exit(1)

        runner_instance.initialize_args(unknown_args)
        if args.initialize and hasattr(vehicle, "_preflight_wait"):
            vehicle._preflight_wait(args.initialize)

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

        success = False
        heartbeat_lost = False
        heartbeat_error_cls = getattr(
            api_module, API_CLASS_HEARTBEAT_LOST_ERROR, Exception,
        )
        disconnect_task = None
        try:
            disconnect_task = asyncio.create_task(
                wait_for_v1_connection_loss(
                    vehicle=vehicle,
                    heartbeat_timeout=args.heartbeat_timeout,
                    heartbeat_error_cls=heartbeat_error_cls,
                ),
            )
            await run_runner_with_disconnect_guard(
                runner=runner_instance,
                vehicle=vehicle,
                disconnect_future=disconnect_task,
            )
            success = True
        except Exception as e:
            heartbeat_lost = isinstance(e, heartbeat_error_cls)
            logger.error(f"Experiment failed: {e}")
            traceback.print_exc()
        finally:
            if disconnect_task is not None and not disconnect_task.done():
                disconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await disconnect_task
            if vehicle:
                if (
                    not getattr(vehicle, "_closed")
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
        logger.error(f"Fatal error during v1 execution: {e}")
        traceback.print_exc()

    sys.exit(0 if experiment_success else 1)
