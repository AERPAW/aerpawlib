"""Run experimenter scripts using the v1 API."""

import asyncio
import logging
import os
import signal
import sys
import time
import traceback

from aerpawlib.cli.constants import (
    VEHICLE_CONNECT_POLL_INTERVAL_S,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_ROVER,
    VEHICLE_TYPE_NONE,
    API_CLASS_VEHICLE,
    API_CLASS_DRONE,
    API_CLASS_ROVER,
    API_CLASS_DUMMY_VEHICLE,
    API_CLASS_AERPAW_PLATFORM,
    API_CLASS_HEARTBEAT_LOST_ERROR,
    VEHICLE_ATTR_INTERNAL_CONNECTED,
    VEHICLE_ATTR_CLOSED,
    EVENT_MISSION_START,
    EVENT_MISSION_END,
    INVALID_VEHICLE_TYPE_MSG,
    STANDALONE_MODE_MSG,
)

from .disconnect import (
    run_runner_with_disconnect_guard,
    wait_for_v1_connection_loss,
)
from .discovery import discover_runner

from aerpawlib.cli.constants import AERPAWLIB_LOGGER_NAME

logger = logging.getLogger(AERPAWLIB_LOGGER_NAME)


def run_v1_experiment(
    args, unknown_args, api_module, experimenter_script, version_name="v1"
):
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
    }.get(args.vehicle, None)

    if vehicle_type is None:
        logger.error(f"Invalid vehicle type: {args.vehicle}")
        raise Exception(INVALID_VEHICLE_TYPE_MSG)

    logger.info(f"Starting experiment execution ({version_name})")

    async def run_experiment_async():
        event_log = None
        logger.info("Connecting to vehicle...")
        try:

            async def create_vehicle_inner():
                v = await asyncio.to_thread(vehicle_type, args.conn, args.mavsdk_port)
                if hasattr(v, VEHICLE_ATTR_INTERNAL_CONNECTED):
                    start = time.time()
                    while (
                        not getattr(v, VEHICLE_ATTR_INTERNAL_CONNECTED)
                        and (time.time() - start) < args.conn_timeout
                    ):
                        await asyncio.sleep(VEHICLE_CONNECT_POLL_INTERVAL_S)
                    if not getattr(v, VEHICLE_ATTR_INTERNAL_CONNECTED):
                        raise TimeoutError("Connection timeout")
                return v

            vehicle = await asyncio.wait_for(
                create_vehicle_inner(), timeout=args.conn_timeout
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
            event_log.log_event(EVENT_MISSION_START)
            logger.info("Structured event logging -> %s", args.structured_log)

        def handle_shutdown(signum, frame):
            logger.warning("Initiating graceful shutdown...")
            if vehicle:
                vehicle.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        no_aerpaw_env = getattr(args, "no_aerpaw_environment", False)
        if no_aerpaw_env:
            logger.info(STANDALONE_MODE_MSG)
            if AERPAW_Platform:
                AERPAW_Platform._no_stdout = args.no_stdout
        elif AERPAW_Platform:
            AERPAW_Platform._no_stdout = args.no_stdout
            _attempt_connect = AERPAW_Platform._connected
            if not AERPAW_Platform._connected:
                logger.critical(
                    "It seems like we're in standalone mode but "
                    "--no-aerpaw-environment was not passed. "
                    "Pass --no-aerpaw-environment to run outside the AERPAW "
                    "environment."
                )
                sys.exit(1)

        runner_instance.initialize_args(unknown_args)
        if args.initialize and hasattr(vehicle, "_preflight_wait"):
            vehicle._preflight_wait(args.initialize)

        if flag_zmq_runner:
            if not args.zmq_identifier or not args.zmq_server_addr:
                logger.error(
                    "ZMQ runner requires --zmq-identifier and --zmq-proxy-server. "
                    "Example: --zmq-identifier leader --zmq-proxy-server 127.0.0.1"
                )
                raise ValueError(
                    "ZMQ runners require --zmq-identifier and --zmq-proxy-server"
                )
            runner_instance._initialize_zmq_bindings(
                args.zmq_identifier, args.zmq_server_addr
            )

        success = False
        heartbeat_lost = False
        heartbeat_error_cls = getattr(
            api_module, API_CLASS_HEARTBEAT_LOST_ERROR, Exception
        )
        disconnect_task = None
        try:
            disconnect_task = asyncio.create_task(
                wait_for_v1_connection_loss(
                    vehicle=vehicle,
                    heartbeat_timeout=args.heartbeat_timeout,
                    heartbeat_error_cls=heartbeat_error_cls,
                )
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
                try:
                    await disconnect_task
                except asyncio.CancelledError:
                    pass
            if vehicle:
                if (
                    not getattr(vehicle, VEHICLE_ATTR_CLOSED)
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
                try:
                    event_log.log_event(EVENT_MISSION_END, success=success)
                except Exception:
                    pass
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
