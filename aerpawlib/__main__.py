"""
Tool used to run aerpawlib scripts that make use of a Runner class.

usage:
    aerpawlib --script <script path> --conn <connection string> \
            --vehicle <vehicle type>

example:
    aerpawlib --script my_mission.py --conn /dev/ttyACM0 \
            --vehicle drone

    aerpawlib --script my_mission.py --conn udpin://127.0.0.1:14550 \
            --vehicle drone
"""

# Removed static imports so we can select API version at runtime
# (the appropriate modules will be imported after parsing CLI args)

import asyncio
import importlib
import importlib.util
import inspect
import json
import logging
import os
import signal
import sys
import time
import traceback
from argparse import ArgumentParser
from typing import Optional

from aerpawlib.log import ColoredFormatter


# Configure logging
def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure logging for aerpawlib and user scripts.

    Configures the root logger so that logs from all modules (aerpawlib,
    user scripts, and libraries) are captured and formatted consistently.

    Args:
        verbose: Enable debug (DEBUG level) logging
        quiet: Suppress most output (WARNING level only)
        log_file: Optional path to write logs to file

    Returns:
        Configured logger instance
    """
    # Configure the ROOT logger to capture logs from all modules
    root_logger = logging.getLogger()

    # Determine log level: quiet=WARNING, default=INFO, verbose=DEBUG
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    root_logger.setLevel(level)

    # Remove existing handlers to prevent duplicates
    root_logger.handlers.clear()

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter(use_colors=True))
    root_logger.addHandler(console_handler)

    # Suppress noisy external logs
    logging.getLogger("_cython.cygrpc").setLevel(logging.WARNING)
    logging.getLogger("grpc._cython.cygrpc").setLevel(logging.WARNING)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Return the aerpawlib-specific logger for the main module
    return logging.getLogger("aerpawlib")


# Global logger instance (configured in main())
logger: Optional[logging.Logger] = None


def _is_direct_user_runner_class(
    candidate, runner_cls, framework_runner_classes
):
    """True when candidate is a user runner directly inheriting a framework runner.

    We intentionally disallow user-defined runner inheritance chains (e.g.
    ``MyRunnerBase(StateMachine)`` then ``Mission(MyRunnerBase)``) to keep
    discovery unambiguous and consistent with the expected API usage.
    """
    if not inspect.isclass(candidate):
        return False
    if not issubclass(candidate, runner_cls):
        return False
    if candidate in framework_runner_classes:
        return False
    return any(base in framework_runner_classes for base in candidate.__bases__)


def discover_runner(api_module, experimenter_script):
    """Search for a Runner class in the experimenter script."""
    Runner = getattr(api_module, "Runner")
    StateMachine = getattr(api_module, "StateMachine")
    BasicRunner = getattr(api_module, "BasicRunner")
    # ZmqStateMachine only exists in v1
    ZmqStateMachine = getattr(api_module, "ZmqStateMachine", None)
    framework_runner_classes = [Runner, StateMachine, BasicRunner]
    if ZmqStateMachine:
        framework_runner_classes.append(ZmqStateMachine)

    runner = None
    flag_zmq_runner = False

    logger.debug("Searching for Runner class in script...")
    for name, val in inspect.getmembers(experimenter_script):
        if not _is_direct_user_runner_class(
            val, Runner, framework_runner_classes
        ):
            continue
        if ZmqStateMachine and issubclass(val, ZmqStateMachine):
            flag_zmq_runner = True
            logger.debug(f"Found ZmqStateMachine: {name}")
        if runner:
            logger.error("Multiple Runner classes found in script")
            raise Exception("You can only define one runner")
        logger.info(f"Found runner class: {name}")
        runner = val()

    if runner is None:
        logger.error("No Runner class found in script")
        raise Exception("No Runner class found in script")

    return runner, flag_zmq_runner


def run_v2_experiment(
    args, unknown_args, api_module, experimenter_script, start_time=None
):
    """Run an experiment using the v2 API."""
    Runner = getattr(api_module, "Runner")
    StateMachine = getattr(api_module, "StateMachine")
    BasicRunner = getattr(api_module, "BasicRunner")
    ZmqStateMachine = getattr(api_module, "ZmqStateMachine", None)
    framework_runner_classes = [Runner, StateMachine, BasicRunner]
    if ZmqStateMachine:
        framework_runner_classes.append(ZmqStateMachine)

    runner = None
    flag_zmq_runner = False
    logger.debug("Searching for Runner class in script...")
    for name, val in inspect.getmembers(experimenter_script):
        if not _is_direct_user_runner_class(
            val, Runner, framework_runner_classes
        ):
            continue
        if ZmqStateMachine and issubclass(val, ZmqStateMachine):
            flag_zmq_runner = True
            logger.debug(f"Found ZmqStateMachine: {name}")
        if runner:
            logger.error("Multiple Runner classes found in script")
            raise Exception("You can only define one runner")
        logger.info(f"Found runner class: {name}")
        runner = val()

    if runner is None:
        logger.error("No Runner class found in script")
        raise Exception("No Runner class found in script")

    Vehicle = getattr(api_module, "Vehicle")
    Drone = getattr(api_module, "Drone")
    Rover = getattr(api_module, "Rover")
    DummyVehicle = getattr(api_module, "DummyVehicle", None)
    AERPAW_Platform = getattr(api_module, "AERPAW_Platform", None)

    vehicle_type = {
        "generic": Vehicle,
        "drone": Drone,
        "rover": Rover,
        "none": DummyVehicle,
    }.get(args.vehicle, None)

    if vehicle_type is None:
        logger.error(f"Invalid vehicle type: {args.vehicle}")
        raise Exception("Please specify a valid vehicle type")

    logger.info("Starting experiment execution (v2)")
    if args.debug_dump:
        logger.warning("--debug-dump is not yet implemented for --api-version v2; flag ignored")

    async def run_experiment_async():
        no_aerpaw_env = getattr(args, "no_aerpaw_environment", False)

        if no_aerpaw_env:
            aerpaw_platform = None
            logger.info(
                "--no-aerpaw-environment set: skipping AERPAW platform connection, "
                "running in standalone mode."
            )
        elif AERPAW_Platform:
            aerpaw_platform = AERPAW_Platform()
            aerpaw_platform.set_no_stdout(args.no_stdout)
            if not aerpaw_platform._connected:
                logger.critical(
                    "It seems like we're in standalone mode but "
                    "--no-aerpaw-environment was not passed. "
                    "Pass --no-aerpaw-environment to run outside the AERPAW "
                    "environment."
                )
                sys.exit(1)
        else:
            aerpaw_platform = None

        from aerpawlib.v2.constants import DEFAULT_SAFETY_CHECKER_PORT
        from aerpawlib.v2.safety import NoOpSafetyChecker, SafetyCheckerClient

        is_aerpaw = aerpaw_platform._connected if aerpaw_platform else False
        effective_port = (
            args.safety_checker_port
            if args.safety_checker_port is not None
            else (DEFAULT_SAFETY_CHECKER_PORT if is_aerpaw else None)
        )
        if effective_port is None:
            safety_client = NoOpSafetyChecker(
                "Not in AERPAW environment and --safety-checker-port not provided."
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
                    "SafetyCheckerServer connection failed (%s:%d): %s. "
                    "Using passthrough (all validations pass).",
                    safety_addr,
                    effective_port,
                    e,
                )
                safety_client = NoOpSafetyChecker(
                    f"Connection to {safety_addr}:{effective_port} failed: {e}"
                )

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
        _conn_handler_ref: list = [None]  # mutable ref so handle_shutdown can access it

        def handle_shutdown():
            logger.warning("Initiating graceful shutdown...")
            shutdown_event.set()
            if _conn_handler_ref[0] is not None:
                _conn_handler_ref[0].stop()
            if vehicle:
                vehicle.close()

        try:
            from aerpawlib.v2.safety.connection import (
                ConnectionHandler,
                setup_signal_handlers,
            )
            loop = asyncio.get_running_loop()
            conn_handler = ConnectionHandler(
                vehicle,
                heartbeat_timeout=args.heartbeat_timeout,
                on_disconnect=lambda: (
                    aerpaw_platform.log_to_oeo(
                        "[aerpawlib] Connection lost", severity="CRITICAL"
                    )
                    if aerpaw_platform
                    else None
                ),
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

        runner.initialize_args(unknown_args)

        # Create shutdown_task early so it can be included in both the
        # preflight wait and the run wait below.
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        success = False
        try:
            if args.initialize and hasattr(vehicle, "_preflight_wait"):
                preflight_task = asyncio.create_task(
                    vehicle._preflight_wait(args.initialize)
                )
                preflight_waits = [preflight_task, shutdown_task]
                if disconnect_future is not None:
                    preflight_waits.append(disconnect_future)
                done, _ = await asyncio.wait(
                    preflight_waits,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if preflight_task not in done:
                    preflight_task.cancel()
                    try:
                        await preflight_task
                    except asyncio.CancelledError:
                        pass
                if shutdown_event.is_set():
                    return success  # finally block handles vehicle.close()
                if disconnect_future is not None and disconnect_future in done:
                    exc = None if disconnect_future.cancelled() else disconnect_future.exception()
                    if exc is not None:
                        raise exc

            if flag_zmq_runner:
                if not args.zmq_identifier or not args.zmq_server_addr:
                    logger.error(
                        "ZMQ runner requires --zmq-identifier and --zmq-proxy-server. "
                        "Example: --zmq-identifier leader --zmq-proxy-server 127.0.0.1"
                    )
                    raise ValueError(
                        "ZMQ runners require --zmq-identifier and --zmq-proxy-server"
                    )
                runner._initialize_zmq_bindings(
                    args.zmq_identifier, args.zmq_server_addr
                )

            run_task = asyncio.create_task(runner.run(vehicle))
            tasks = [run_task, shutdown_task]
            if disconnect_future is not None:
                tasks.append(disconnect_future)
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                if hasattr(t, "cancel"):
                    t.cancel()
            if shutdown_event.is_set():
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
            elif disconnect_future is not None and disconnect_future in done:
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                exc = None if disconnect_future.cancelled() else disconnect_future.exception()
                if exc is not None:
                    raise exc
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
                        if args.vehicle == "drone":
                            await vehicle.return_to_launch()
                        elif args.vehicle == "rover" and vehicle.home_coords:
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
        return success

    experiment_success = False
    try:
        experiment_success = asyncio.run(run_experiment_async())
    except Exception as e:
        logger.error(f"Fatal error during v2 execution: {e}")
        traceback.print_exc()

    sys.exit(0 if experiment_success else 1)


def run_v1_experiment(
    args, unknown_args, api_module, experimenter_script, version_name="v1"
):
    """Run an experiment using the v1 API."""
    runner, flag_zmq_runner = discover_runner(api_module, experimenter_script)
    assert runner is not None  # discover_runner raises if no runner found

    Vehicle = getattr(api_module, "Vehicle")
    Drone = getattr(api_module, "Drone")
    Rover = getattr(api_module, "Rover")
    DummyVehicle = getattr(api_module, "DummyVehicle", None)
    AERPAW_Platform = getattr(api_module, "AERPAW_Platform", None)

    vehicle_type = {
        "generic": Vehicle,
        "drone": Drone,
        "rover": Rover,
        "none": DummyVehicle,
    }.get(args.vehicle, None)

    if vehicle_type is None:
        logger.error(f"Invalid vehicle type: {args.vehicle}")
        raise Exception("Please specify a valid vehicle type")

    logger.info(f"Starting experiment execution ({version_name})")

    async def run_experiment_async():
        # Connection
        logger.info("Connecting to vehicle...")
        try:
            async def create_vehicle_inner():
                # Run blocking constructor off event loop to keep it responsive
                v = await asyncio.to_thread(vehicle_type, args.conn, args.mavsdk_port)
                if hasattr(v, "_connected"):
                    start = time.time()
                    while (
                        not v._connected
                        and (time.time() - start) < args.conn_timeout
                    ):
                        await asyncio.sleep(0.1)
                    if not v._connected:
                        raise TimeoutError("Connection timeout")
                return v

            vehicle = await asyncio.wait_for(
                create_vehicle_inner(), timeout=args.conn_timeout
            )
        except Exception as e:
            raise ConnectionError(f"Could not connect: {e}")

        # Shutdown
        def handle_shutdown(signum, frame):
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
                "running in standalone mode."
            )
            if AERPAW_Platform:
                AERPAW_Platform._no_stdout = args.no_stdout
        elif AERPAW_Platform:
            AERPAW_Platform._no_stdout = args.no_stdout
            # Force eager initialisation of the lazy proxy so _connected is set
            _attempt_connect = AERPAW_Platform._connected
            if not AERPAW_Platform._connected:
                logger.critical(
                    "It seems like we're in standalone mode but "
                    "--no-aerpaw-environment was not passed. "
                    "Pass --no-aerpaw-environment to run outside the AERPAW "
                    "environment."
                )
                sys.exit(1)

        runner.initialize_args(unknown_args)
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
            runner._initialize_zmq_bindings(
                args.zmq_identifier, args.zmq_server_addr
            )

        success = False
        try:
            await runner.run(vehicle)
            success = True
        except Exception as e:
            logger.error(f"Experiment failed: {e}")
            traceback.print_exc()
        finally:
            # RTL/Cleanup
            if vehicle:
                if (
                    not vehicle._closed
                    and vehicle.armed
                    and args.rtl_at_end
                ):
                    logger.warning("Vehicle still armed! RTLing...")
                    try:
                        if args.vehicle == "drone":
                            await vehicle.return_to_launch()
                        elif args.vehicle == "rover" and vehicle.home_coords:
                            await vehicle.goto_coordinates(vehicle.home_coords)
                    except Exception as e:
                        logger.error(f"RTL failed: {e}")
                        traceback.print_exc()
                vehicle.close()
        return success

    experiment_success = False
    try:
        experiment_success = asyncio.run(run_experiment_async())
    except Exception as e:
        logger.error(f"Fatal error during v1 execution: {e}")
        traceback.print_exc()

    sys.exit(0 if experiment_success else 1)


def main():
    """Main entry point for aerpawlib CLI."""
    # Import trick to allow things to work when run as "aerpawlib"

    current_file = os.path.abspath(__file__)

    #  Go up two levels to find the Project Root
    #    Level 1: /.../aerpawlib-vehicle-control/aerpawlib
    #    Level 2: /.../aerpawlib-vehicle-control (Where 'examples' lives)
    project_root = os.path.dirname(os.path.dirname(current_file))

    # Set the Process CWD to the Project Root
    #    (This does NOT change the terminal's path, only this running process)
    os.chdir(project_root)
    sys.path.insert(0, os.getcwd())

    # Pre-parse for config file
    conf_parser = ArgumentParser(add_help=False)
    conf_parser.add_argument(
        "--config", help="path to JSON configuration file"
    )
    conf_args, _ = conf_parser.parse_known_args()

    cli_args = sys.argv[1:]

    # If config file is provided, load it and merge arguments
    if conf_args.config:
        if not os.path.exists(conf_args.config):
            print(f"Config file not found: {conf_args.config}")
            sys.exit(1)

        try:
            with open(conf_args.config, "r") as f:
                config_data = json.load(f)

            config_cli_args = []
            for key, value in config_data.items():
                if isinstance(value, bool):
                    if value:
                        config_cli_args.append(f"--{key}")
                    # for store_false args, if user puts "skip-init": false in json,
                    # it means they DON'T want to skip init (which is default).
                    # So we don't add --skip-init flag.
                    # if user puts "skip-init": true, we add --skip-init.
                elif isinstance(value, list):
                    for item in value:
                        config_cli_args.append(f"--{key}")
                        config_cli_args.append(str(item))
                else:
                    config_cli_args.append(f"--{key}")
                    config_cli_args.append(str(value))

            # Prepend config args to CLI args so CLI overrides config
            cli_args = config_cli_args + cli_args

        except Exception as e:
            print(f"Error loading config file: {e}")
            sys.exit(1)

    proxy_mode = "--run-proxy" in cli_args

    parser = ArgumentParser(
        description="aerpawlib - wrap and run aerpaw experimenter scripts"
    )
    parser.add_argument(
        "--config",
        help="path to JSON configuration file. Keys are other arguments.\n"
        "Providing arguments to aerpawlib will override the config file.",
    )

    # Core Arguments
    core_grp = parser.add_argument_group("Core Arguments")
    core_grp.add_argument(
        "--script", help="path to experimenter script (e.g. my_mission.py)", required=not proxy_mode
    )
    core_grp.add_argument(
        "--conn", "--connection", help="connection string", required=not proxy_mode
    )
    core_grp.add_argument(
        "--vehicle",
        help="vehicle type",
        choices=["generic", "drone", "rover", "none"],
        required=not proxy_mode,
    )
    core_grp.add_argument(
        "--api-version",
        help="which API version to use (v1 or v2)",
        choices=["v1", "v2"],
        default="v1",
    )

    # Execution Flags
    exec_grp = parser.add_argument_group("Execution Flags")
    exec_grp.add_argument(
        "--skip-init",
        help="skip initialization",
        action="store_false",
        dest="initialize",
    )
    exec_grp.add_argument(
        "--skip-rtl",
        help="don't rtl and land at the end of an experiment automatically",
        action="store_false",
        dest="rtl_at_end",
    )
    exec_grp.add_argument(
        "--debug-dump",
        help="run aerpawlib's internal debug dump on vehicle object",
        action="store_true",
        dest="debug_dump",
    )
    exec_grp.add_argument(
        "--no-aerpawlib-stdout",
        help="prevent aerpawlib from printing to stdout",
        action="store_true",
        dest="no_stdout",
    )
    exec_grp.add_argument(
        "--no-aerpaw-environment",
        help="run in standalone/SITL mode: skip AERPAW platform connection and "
        "allow the vehicle to arm itself. Without this flag, a failed AERPAW "
        "connection is treated as a fatal error.",
        action="store_true",
        dest="no_aerpaw_environment",
    )

    # ZMQ Proxy Arguments
    zmq_grp = parser.add_argument_group("ZMQ Proxy")
    zmq_grp.add_argument(
        "--run-proxy",
        help="run zmq proxy",
        action="store_true",
        dest="run_zmq_proxy",
    )
    zmq_grp.add_argument(
        "--zmq-identifier", help="zmq identifier", dest="zmq_identifier"
    )
    zmq_grp.add_argument(
        "--zmq-proxy-server",
        help="zmq proxy server addr",
        dest="zmq_server_addr",
    )

    # Logging Arguments
    log_grp = parser.add_argument_group("Logging")
    log_grp.add_argument(
        "-v",
        "--verbose",
        help="enable debug logging (DEBUG level)",
        action="store_true",
    )
    log_grp.add_argument(
        "-q",
        "--quiet",
        help="suppress most output (WARNING level only)",
        action="store_true",
    )
    log_grp.add_argument(
        "--log-file",
        help="write logs to file in addition to console",
        dest="log_file",
    )

    # Connection Handling Arguments
    conn_grp = parser.add_argument_group("Connection Tuning")
    conn_grp.add_argument(
        "--conn-timeout", "--connection-timeout",
        help="initial connection timeout in seconds (default: 30)",
        type=float,
        default=30.0,
        dest="conn_timeout",
    )
    conn_grp.add_argument(
        "--heartbeat-timeout",
        help="max seconds without heartbeat before considered disconnected (default: 5)",
        type=float,
        default=5.0,
        dest="heartbeat_timeout",
    )
    conn_grp.add_argument(
        "--mavsdk-port",
        help="gRPC port for the embedded mavsdk_server (default: 50051). "
        "Use a unique port per vehicle process to avoid conflicts when running "
        "multiple vehicles on the same host.",
        type=int,
        default=50051,
        dest="mavsdk_port",
    )
    conn_grp.add_argument(
        "--safety-checker-port",
        help="Port for SafetyCheckerServer (v2 only). In AERPAW env defaults to 14580; "
        "outside AERPAW, optional. If connection fails: AERPAW=crash, non-AERPAW=passthrough.",
        type=int,
        default=None,
        dest="safety_checker_port",
    )

    args, unknown_args = parser.parse_known_args(
        args=cli_args
    )  # we'll pass other args to the script

    # Filter out empty strings from unknown_args which can be caused by trailing
    # spaces or empty quoted arguments in some shell environments
    unknown_args = [arg for arg in unknown_args if arg != ""]

    # Initialize logging based on command line arguments
    global logger
    logger = setup_logging(
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file,
    )

    # Start timing for performance debugging
    global start_time
    start_time = time.time()

    # Log startup information
    logger.info("aerpawlib - AERPAW Vehicle Control Library")
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Working directory: {os.getcwd()}")
    logger.debug(f"API version: {args.api_version}")
    logger.debug(f"Script: {args.script}")
    logger.debug(f"Vehicle type: {args.vehicle}")
    logger.debug(f"Connection string: {args.conn}")
    logger.debug(f"Additional arguments: {unknown_args}")
    logger.debug(f"No AERPAW environment: {args.no_aerpaw_environment}")

    # Dynamically import API module
    api_version = args.api_version
    logger.debug(f"Loading API version: {api_version}")
    try:
        api_module = importlib.import_module(f"aerpawlib.{api_version}")
        logger.debug(
            f"Time to import API module: {time.time() - start_time:.2f}s"
        )
        # Inject into globals for backward compatibility in some scripts if needed
        # Use __all__ if defined, otherwise filter out standard modules
        if hasattr(api_module, "__all__"):
            for name in api_module.__all__:
                globals()[name] = getattr(api_module, name)
        else:
            for name in dir(api_module):
                if not name.startswith("_"):
                    # Don't overwrite standard modules that we've already imported
                    if name in ["logging", "os", "sys", "time", "asyncio", "json", "signal", "traceback"]:
                        continue
                    globals()[name] = getattr(api_module, name)
    except Exception as e:
        logger.error(f"Failed to import aerpawlib {api_version}: {e}")
        sys.exit(1)

    if args.run_zmq_proxy:
        logger.info("Starting ZMQ proxy mode")
        if hasattr(api_module, "run_zmq_proxy"):
            api_module.run_zmq_proxy()
        else:
            logger.error(f"API {api_version} does not support ZMQ proxy")
        sys.exit(0)

    # import script
    logger.debug(f"Loading experimenter script: {args.script}")
    start_time = time.time()  # reset timer for script import
    try:
        script_arg = args.script
        # Accept file paths (e.g. "my_mission.py", "examples/v1/basic_example.py", "examples/v1/basic_example")
        # or dotted module names (e.g. "examples.v1.basic_example")
        if os.sep in script_arg or "/" in script_arg or script_arg.endswith(".py"):
            script_path = script_arg if script_arg.endswith(".py") else script_arg + ".py"
            module_name = os.path.splitext(os.path.basename(script_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            experimenter_script = importlib.util.module_from_spec(spec)
            if spec.loader is None:
                raise ImportError(
                    f"Cannot load module from {script_path}: no loader available"
                )
            spec.loader.exec_module(experimenter_script)
        else:
            experimenter_script = importlib.import_module(script_arg)
        logger.debug(
            f"Time to import experimenter script: {time.time() - start_time:.2f}s"
        )
    except Exception as e:
        logger.error(f"Failed to import script '{args.script}': {e}")
        sys.exit(1)

    # Dispatch to version-specific runner
    if api_version == "v2":
        run_v2_experiment(
            args, unknown_args, api_module, experimenter_script, start_time
        )
    elif api_version == "v1":
        run_v1_experiment(
            args,
            unknown_args,
            api_module,
            experimenter_script,
            version_name="v1",
        )


if __name__ == "__main__":
    main()
