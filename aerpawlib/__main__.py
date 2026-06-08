"""Tool used to run aerpawlib scripts that make use of a Runner class.

usage:
    aerpawlib --script <script path> --conn <connection string> \
            --vehicle <vehicle type>

example:
    aerpawlib --script my_mission.py --conn /dev/ttyACM0 \
            --vehicle drone

    aerpawlib --script my_mission.py --conn udpin://127.0.0.1:14550 \
            --vehicle drone
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import typer

from aerpawlib.cli.config_merge import (
    config_dict_to_cli_args,
    merge_config_json_files,
    strip_config_argv,
)
from aerpawlib.cli.constants import (
    DEFAULT_CONNECTION_TIMEOUT_S,
    DEFAULT_HEARTBEAT_TIMEOUT_S,
    DEFAULT_MAVSDK_PORT,
    DEFAULT_SAFETY_CHECKER_PORT,
    VEHICLE_TYPE_DRONE,
    VEHICLE_TYPE_GENERIC,
    VEHICLE_TYPE_NONE,
    VEHICLE_TYPE_ROVER,
)
from aerpawlib.cli.experiments_v1 import run_v1_experiment
from aerpawlib.cli.experiments_v2 import run_v2_experiment
from aerpawlib.cli.logging_setup import setup_logging
from aerpawlib.cli.paths import (
    find_repo_root_containing_examples,
    resolve_cli_path,
    resolve_script_path,
)

logger: logging.Logger
start_time: float

app = typer.Typer(
    help="aerpawlib - wrap and run aerpaw experimenter scripts",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback(
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    script: str = typer.Option(
        ...,
        "--script",
        help="The path to the experimenter mission script to run (e.g. 'my_mission.py' or 'examples/v1/basic_runner.py').",
        rich_help_panel="Core Options",
    ),
    conn: str = typer.Option(
        ...,
        "--conn",
        "--connection",
        help="The vehicle MAVLink connection string (e.g., 'udpin://127.0.0.1:14550' or '/dev/ttyACM0').",
        rich_help_panel="Core Options",
    ),
    vehicle: str = typer.Option(
        ...,
        "--vehicle",
        help=f"The type of vehicle being controlled ('{VEHICLE_TYPE_GENERIC}', '{VEHICLE_TYPE_DRONE}', '{VEHICLE_TYPE_ROVER}', or '{VEHICLE_TYPE_NONE}').",
        rich_help_panel="Core Options",
    ),
    api_version: str = typer.Option(
        "v1",
        "--api-version",
        help="The version of the vehicle control API to use ('v1' or 'v2').",
        rich_help_panel="Core Options",
    ),
    config: list[str] | None = typer.Option(
        None,
        "--config",
        help="JSON configuration file(s) of CLI option defaults. Can be specified multiple times; later files override earlier ones.",
        rich_help_panel="Configuration Options",
    ),
    skip_init: bool = typer.Option(
        False,
        "--skip-init",
        help="Skip the preflight wait and vehicle initialization phase.",
        rich_help_panel="Execution Options",
    ),
    skip_rtl: bool = typer.Option(
        False,
        "--skip-rtl",
        help="Do not trigger an automatic Return-To-Launch (RTL) and land sequence at the end of the experiment.",
        rich_help_panel="Execution Options",
    ),
    no_aerpaw_environment: bool = typer.Option(
        False,
        "--no-aerpaw-environment",
        help="Run in standalone/SITL simulation mode. Disables AERPAW platform connection requirements and permits automatic self-arming.",
        rich_help_panel="Connection & Safety Options",
    ),
    conn_timeout: float = typer.Option(
        DEFAULT_CONNECTION_TIMEOUT_S,
        "--conn-timeout",
        "--connection-timeout",
        help="Maximum time in seconds to wait for the initial vehicle connection before timing out.",
        rich_help_panel="Connection & Safety Options",
    ),
    heartbeat_timeout: float = typer.Option(
        DEFAULT_HEARTBEAT_TIMEOUT_S,
        "--heartbeat-timeout",
        help="Maximum seconds to wait without receiving a heartbeat message from the vehicle before raising a disconnect error.",
        rich_help_panel="Connection & Safety Options",
    ),
    mavsdk_port: int = typer.Option(
        DEFAULT_MAVSDK_PORT,
        "--mavsdk-port",
        help="The gRPC port to use for the embedded MAVSDK server. Useful when running multiple simulators.",
        rich_help_panel="Connection & Safety Options",
    ),
    safety_checker_port: int | None = typer.Option(
        None,
        "--safety-checker-port",
        help=f"The ZMQ port for the AERPAW SafetyCheckerServer (v2 only). Defaults to {DEFAULT_SAFETY_CHECKER_PORT} in AERPAW environments.",
        rich_help_panel="Connection & Safety Options",
    ),
    safety_checker_ip: str = typer.Option(
        "127.0.0.1",
        "--safety-checker-ip",
        help="The IP/host address for the AERPAW SafetyCheckerServer (v2 only).",
        rich_help_panel="Connection & Safety Options",
    ),
    zmq_identifier: str | None = typer.Option(
        None,
        "--zmq-identifier",
        help="Unique node identifier string when running under a multi-vehicle ZMQ state machine (e.g., 'leader').",
        rich_help_panel="ZMQ Orchestration Options",
    ),
    zmq_proxy_server: str | None = typer.Option(
        None,
        "--zmq-proxy-server",
        help="The connection address of the ZMQ proxy server (e.g., '127.0.0.1').",
        rich_help_panel="ZMQ Orchestration Options",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Enable detailed debug-level logging output (DEBUG level).",
        rich_help_panel="Output & Logging Options",
    ),
    quiet: bool = typer.Option(
        False,
        "-q",
        "--quiet",
        help="Suppress regular output and log warnings/errors only (WARNING level).",
        rich_help_panel="Output & Logging Options",
    ),
    log_file: str | None = typer.Option(
        None,
        "--log-file",
        help="Path to a file where all log output will be written in addition to the console.",
        rich_help_panel="Output & Logging Options",
    ),
    structured_log: str | None = typer.Option(
        None,
        "--structured-log",
        help="Path to output a JSONL structured event log file for the mission.",
        rich_help_panel="Output & Logging Options",
    ),
    no_stdout: bool = typer.Option(
        False,
        "--no-aerpawlib-stdout",
        help="Mute all console stdout output from the aerpawlib library.",
        rich_help_panel="Output & Logging Options",
    ),
) -> None:
    """Run aerpawlib experimenter scripts."""
    global logger, start_time

    invocation_cwd = Path.cwd().resolve()
    unknown_args = [arg for arg in ctx.args if arg != ""]

    if vehicle and vehicle not in [
        VEHICLE_TYPE_GENERIC,
        VEHICLE_TYPE_DRONE,
        VEHICLE_TYPE_ROVER,
        VEHICLE_TYPE_NONE,
    ]:
        typer.echo(f"Error: Invalid choice for --vehicle: {vehicle}")
        raise typer.Exit(code=1)

    if api_version not in ["v1", "v2"]:
        typer.echo(f"Error: Invalid choice for --api-version: {api_version}")
        raise typer.Exit(code=1)

    args = SimpleNamespace(
        config=config,
        script=script,
        conn=conn,
        vehicle=vehicle,
        api_version=api_version,
        initialize=not skip_init,
        rtl_at_end=not skip_rtl,
        no_stdout=no_stdout,
        no_aerpaw_environment=no_aerpaw_environment,
        run_zmq_proxy=False,
        zmq_identifier=zmq_identifier,
        zmq_proxy_server=zmq_proxy_server,
        verbose=verbose,
        quiet=quiet,
        log_file=log_file,
        structured_log=structured_log,
        conn_timeout=conn_timeout,
        heartbeat_timeout=heartbeat_timeout,
        mavsdk_port=mavsdk_port,
        safety_checker_port=safety_checker_port,
        safety_checker_ip=safety_checker_ip,
    )

    if args.log_file:
        args.log_file = str(resolve_cli_path(args.log_file, str(invocation_cwd)))
    if args.structured_log:
        args.structured_log = str(
            resolve_cli_path(args.structured_log, str(invocation_cwd)),
        )
    if args.script:
        sa = args.script
        if "/" in sa or sa.endswith(".py"):
            args.script = resolve_script_path(sa, str(invocation_cwd))

    if args.verbose:
        level = logging.DEBUG
    elif args.quiet and not args.verbose:
        level = logging.WARNING
    else:
        level = logging.INFO

    from aerpawlib.cli.progress_bar import start_progress, stop_progress

    # Start the progress bar before setting up logging so RichHandler binds to the progress console
    start_progress(enabled=not args.no_stdout)

    try:
        logger = setup_logging(
            level=level,
            log_file=args.log_file,
        )

        start_time = time.time()

        logger.info("aerpawlib - AERPAW Vehicle Control Library")
        logger.debug(f"Python version: {sys.version}")
        logger.debug(f"Invocation directory: {invocation_cwd}")
        logger.debug(f"Working directory (project root): {Path.cwd()}")
        logger.debug(f"API version: {args.api_version}")
        logger.debug(f"Script: {args.script}")
        logger.debug(f"Vehicle type: {args.vehicle}")
        logger.debug(f"Connection string: {args.conn}")
        logger.debug(f"Additional arguments: {unknown_args}")
        logger.debug(f"No AERPAW environment: {args.no_aerpaw_environment}")

        logger.debug(f"Loading experimenter script: {args.script}")
        start_time = time.time()
        try:
            script_arg = args.script
            if "/" in script_arg or script_arg.endswith(".py"):
                script_path = script_arg if script_arg.endswith(".py") else script_arg + ".py"
                script_p = Path(script_path)
                module_name = script_p.stem
                spec = importlib.util.spec_from_file_location(module_name, str(script_path))
                if spec is None:
                    raise ImportError(
                        f"Cannot load experimenter module from '{script_path}'",
                    )
                experimenter_script = importlib.util.module_from_spec(spec)
                if spec.loader is None:
                    raise ImportError(
                        f"Cannot load module from {script_path}: no loader available",
                    )
                spec.loader.exec_module(experimenter_script)
            else:
                experimenter_script = importlib.import_module(script_arg)
            logger.debug(
                f"Time to import experimenter script: {time.time() - start_time:.2f}s",
            )
        except Exception as e:
            logger.error(f"Failed to import script '{args.script}': {e}")
            raise typer.Exit(code=1) from e

        if api_version == "v1":
            run_v1_experiment(args, unknown_args, experimenter_script)
        elif api_version == "v2":
            run_v2_experiment(args, unknown_args, experimenter_script)
    finally:
        stop_progress()


def main() -> None:
    """Main entry point for aerpawlib CLI."""
    invocation_cwd = Path.cwd().resolve()

    current_file = Path(__file__).resolve()

    project_root_path = find_repo_root_containing_examples()
    if project_root_path:
        project_root = Path(project_root_path)
    else:
        project_root = current_file.parent.parent

    project_root_str = str(project_root)
    import os

    os.chdir(project_root_str)
    sys.path.insert(0, project_root_str)

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

    if not cli_args:
        cli_args = ["--help"]

    if config_paths:
        resolved_config_paths = [resolve_cli_path(p, str(invocation_cwd)) for p in config_paths]
        for path in resolved_config_paths:
            if not path.exists():
                print(f"Config file not found: {path}")
                sys.exit(1)
        try:
            merged = merge_config_json_files([str(p) for p in resolved_config_paths])
            config_cli_args = config_dict_to_cli_args(merged)
            cli_args = config_cli_args + strip_config_argv(sys.argv[1:])
        except Exception as e:
            print(f"Error loading config file(s): {e}")
            sys.exit(1)

    app(args=cli_args)


if __name__ == "__main__":
    main()
