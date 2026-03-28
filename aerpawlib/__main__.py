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

import importlib
import importlib.util
import logging
import os
import sys
import time
from argparse import ArgumentParser
from typing import Optional

from aerpawlib.cli.config_merge import (
    config_dict_to_cli_args,
    merge_config_json_files,
    strip_config_argv,
)
from aerpawlib.cli.disconnect import (
    run_runner_with_disconnect_guard as _run_runner_with_disconnect_guard,
    wait_for_v1_connection_loss as _wait_for_v1_connection_loss,
)
from aerpawlib.cli.discovery import discover_runner
from aerpawlib.cli.experiments_v1 import run_v1_experiment
from aerpawlib.cli.experiments_v2 import run_v2_experiment
from aerpawlib.cli.logging_setup import setup_logging
from aerpawlib.cli.paths import (
    find_repo_root_containing_examples,
    resolve_cli_path,
    resolve_script_path,
)
from aerpawlib.cli.constants import (
    DEFAULT_CONNECTION_TIMEOUT_S,
    DEFAULT_HEARTBEAT_TIMEOUT_S,
    DEFAULT_MAVSDK_PORT,
    DEFAULT_SAFETY_CHECKER_PORT,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_ROVER,
    VEHICLE_TYPE_NONE,
)

logger: Optional[logging.Logger] = None
start_time: Optional[float] = None


def main():
    """Main entry point for aerpawlib CLI."""
    global logger, start_time

    # Paths the user passes on the command line are relative to the shell's cwd
    # at invocation, not the project root we chdir to below.
    invocation_cwd = os.path.abspath(os.getcwd())

    current_file = os.path.abspath(__file__)

    project_root = find_repo_root_containing_examples() or os.path.dirname(
        os.path.dirname(current_file)
    )

    os.chdir(project_root)
    sys.path.insert(0, os.getcwd())

    conf_parser = ArgumentParser(add_help=False)
    conf_parser.add_argument(
        "--config",
        action="append",
        default=None,
        dest="config_files",
        metavar="PATH",
    )
    conf_args, _ = conf_parser.parse_known_args()
    config_paths = conf_args.config_files or []

    cli_args = sys.argv[1:]

    if config_paths:
        resolved_config_paths = [
            resolve_cli_path(p, invocation_cwd) for p in config_paths
        ]
        for path in resolved_config_paths:
            if not os.path.exists(path):
                print(f"Config file not found: {path}")
                sys.exit(1)
        try:
            merged = merge_config_json_files(resolved_config_paths)
            config_cli_args = config_dict_to_cli_args(merged)
            cli_args = config_cli_args + strip_config_argv(sys.argv[1:])
        except Exception as e:
            print(f"Error loading config file(s): {e}")
            sys.exit(1)

    proxy_mode = "--run-proxy" in cli_args

    parser = ArgumentParser(
        description="aerpawlib - wrap and run aerpaw experimenter scripts"
    )
    parser.add_argument(
        "--config",
        action="append",
        metavar="PATH",
        help="JSON file(s) of CLI defaults (repeatable). Merged in order; later "
        "files override earlier. Keys match long option names (e.g. api-version, "
        "conn). JSON null removes a key from the merge. Command-line arguments "
        "override the merged config.",
    )

    core_grp = parser.add_argument_group("Core Arguments")
    core_grp.add_argument(
        "--script",
        help="path to experimenter script (e.g. my_mission.py)",
        required=not proxy_mode,
    )
    core_grp.add_argument(
        "--conn", "--connection", help="connection string", required=not proxy_mode
    )
    core_grp.add_argument(
        "--vehicle",
        help="vehicle type",
        choices=[
            VEHICLE_TYPE_GENERIC,
            VEHICLE_TYPE_DRONE,
            VEHICLE_TYPE_ROVER,
            VEHICLE_TYPE_NONE,
        ],
        required=not proxy_mode,
    )
    core_grp.add_argument(
        "--api-version",
        help="which API version to use (v1 or v2)",
        choices=["v1", "v2"],
        default="v1",
    )

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
    log_grp.add_argument(
        "--structured-log",
        metavar="FILE",
        dest="structured_log",
        help="Emit JSONL event log to FILE (v1 and v2). Omit to disable.",
    )

    conn_grp = parser.add_argument_group("Connection Tuning")
    conn_grp.add_argument(
        "--conn-timeout",
        "--connection-timeout",
        help="initial connection timeout in seconds (default: 30)",
        type=float,
        default=DEFAULT_CONNECTION_TIMEOUT_S,
        dest="conn_timeout",
    )
    conn_grp.add_argument(
        "--heartbeat-timeout",
        help="max seconds without heartbeat before considered disconnected (default: 5)",
        type=float,
        default=DEFAULT_HEARTBEAT_TIMEOUT_S,
        dest="heartbeat_timeout",
    )
    conn_grp.add_argument(
        "--mavsdk-port",
        help="gRPC port for the embedded mavsdk_server (default: 50051). "
        "Use a unique port per vehicle process to avoid conflicts when running "
        "multiple vehicles on the same host.",
        type=int,
        default=DEFAULT_MAVSDK_PORT,
        dest="mavsdk_port",
    )
    conn_grp.add_argument(
        "--safety-checker-port",
        help=f"Port for SafetyCheckerServer (v2 only). In AERPAW env defaults to {DEFAULT_SAFETY_CHECKER_PORT}; "
        "outside AERPAW, optional. If connection fails: AERPAW=crash, non-AERPAW=passthrough.",
        type=int,
        default=None,
        dest="safety_checker_port",
    )
    args, unknown_args = parser.parse_known_args(args=cli_args)

    unknown_args = [arg for arg in unknown_args if arg != ""]

    if args.log_file:
        args.log_file = resolve_cli_path(args.log_file, invocation_cwd)
    if args.structured_log:
        args.structured_log = resolve_cli_path(args.structured_log, invocation_cwd)
    if args.script:
        sa = args.script
        # Dotted module names (no path separators) are resolved by importlib as-is
        if os.sep in sa or "/" in sa or sa.endswith(".py"):
            args.script = resolve_script_path(sa, invocation_cwd)

    logger = setup_logging(
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file,
    )

    start_time = time.time()

    logger.info("aerpawlib - AERPAW Vehicle Control Library")
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Invocation directory: {invocation_cwd}")
    logger.debug(f"Working directory (project root): {os.getcwd()}")
    logger.debug(f"API version: {args.api_version}")
    logger.debug(f"Script: {args.script}")
    logger.debug(f"Vehicle type: {args.vehicle}")
    logger.debug(f"Connection string: {args.conn}")
    logger.debug(f"Additional arguments: {unknown_args}")
    logger.debug(f"No AERPAW environment: {args.no_aerpaw_environment}")

    api_version = args.api_version
    logger.debug(f"Loading API version: {api_version}")
    try:
        api_module = importlib.import_module(f"aerpawlib.{api_version}")
        logger.debug(f"Time to import API module: {time.time() - start_time:.2f}s")
        if hasattr(api_module, "__all__"):
            for name in api_module.__all__:
                globals()[name] = getattr(api_module, name)
        else:
            for name in dir(api_module):
                if not name.startswith("_"):
                    excluded_names = [
                        "logging",
                        "os",
                        "sys",
                        "time",
                        "asyncio",
                        "json",
                        "signal",
                        "traceback",
                    ]
                    if name in excluded_names:
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

    logger.debug(f"Loading experimenter script: {args.script}")
    start_time = time.time()
    try:
        script_arg = args.script
        if os.sep in script_arg or "/" in script_arg or script_arg.endswith(".py"):
            script_path = (
                script_arg if script_arg.endswith(".py") else script_arg + ".py"
            )
            # Already absolute from resolve_cli_path on args.script
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
