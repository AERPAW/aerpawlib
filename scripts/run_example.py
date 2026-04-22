#!/usr/bin/env python3
"""
Run an aerpawlib example script with a bundled SITL.

Starts sim_vehicle.py automatically, waits for it to be ready using UDP port
detection, then launches aerpawlib with the correct connection string. Stops
SITL when the script exits.

Usage:
    aerpawlib-run-example --script examples/v2/basic_example.py --vehicle drone
    aerpawlib-run-example --script examples/v1/basic_example.py --vehicle drone --api-version v1
    aerpawlib-run-example --script examples/v2/rover_example.py --vehicle rover

Any extra arguments are forwarded to aerpawlib unchanged.

Environment variables:
    ARDUPILOT_HOME   Override path to ArduPilot directory
    SITL_VERBOSE     Set to 1 to show raw SITL output (default: silent)
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Defaults mirroring tests/conftest.py
DEFAULT_PORT_DRONE = 14550
DEFAULT_PORT_ROVER = 14560
DEFAULT_INSTANCE_DRONE = 0
DEFAULT_INSTANCE_ROVER = 1
SITL_STARTUP_TIMEOUT = 90


def _find_sim_vehicle() -> Optional[Path]:
    """Locate sim_vehicle.py from ARDUPILOT_HOME or project ardupilot* directories."""
    project_root = Path(__file__).resolve().parent.parent
    ardupilot_dirs = list(project_root.glob("ardupilot*"))

    candidates = [os.environ.get("ARDUPILOT_HOME")] + [
        str(d) for d in ardupilot_dirs if d.is_dir()
    ]

    for base in candidates:
        if base is None:
            continue
        script = Path(base) / "Tools" / "autotest" / "sim_vehicle.py"
        if script.exists():
            return script
    return None


def start_sitl(
    vehicle_type: str,
    port: int,
    instance: int,
    speedup: int,
) -> subprocess.Popen:
    """
    Launch sim_vehicle.py and block until the MAVLink UDP port is ready.

    Readiness is detected by attempting to bind the UDP output port: once
    MAVProxy has claimed it the bind fails with EADDRINUSE, meaning packets
    are flowing.

    Args:
        vehicle_type: ArduPilot vehicle name (e.g. "ArduCopter", "Rover").
        port:         UDP port that sim_vehicle will output MAVLink packets to.
        instance:     SITL instance ID (0 for drone, 1 for rover).
        speedup:      SIM_SPEEDUP value passed as env var.

    Returns:
        The running subprocess.Popen handle.
    """
    sim_vehicle = _find_sim_vehicle()
    if sim_vehicle is None:
        print(
            "ERROR: sim_vehicle.py not found.\n"
            "Run `aerpawlib-setup-sitl` to install SITL, "
            "or set the ARDUPILOT_HOME environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    ardupilot_home = sim_vehicle.parent.parent.parent

    env = os.environ.copy()
    env["ARDUPILOT_HOME"] = str(ardupilot_home)
    env["SIM_SPEEDUP"] = str(speedup)
    # Prevent run_in_terminal_window.sh from opening a GUI window (osascript/xterm).
    # Without DISPLAY the script falls back to running the ArduPilot binary as a
    # background process, which is what we want for headless execution.
    env.pop("DISPLAY", None)

    cmd = [
        sys.executable,
        str(sim_vehicle),
        "-v",
        vehicle_type,
        "-I",
        str(instance),
        f"127.0.0.1:{port}",
        "-w",
    ]

    log_suffix = "drone" if vehicle_type == "ArduCopter" else "rover"
    log_path = Path("/tmp") / f"aerpawlib_sitl_{log_suffix}.log"
    sitl_verbose = os.environ.get("SITL_VERBOSE", "").strip() == "1"

    print(f"Starting SITL ({vehicle_type}) on UDP port {port}...")

    if sitl_verbose:
        stdout_target = None
        stderr_target = None
    else:
        # Use a real file rather than DEVNULL: pexpect inside sim_vehicle.py
        # calls isatty() and misbehaves when stdout is /dev/null.
        _log_file = open(log_path, "w")
        stdout_target = _log_file
        stderr_target = subprocess.STDOUT
        print(f"  SITL log: {log_path}  (set SITL_VERBOSE=1 to stream to terminal)")

    print(f"  Running SITL with command: '{' '.join(cmd)}'")
    process = subprocess.Popen(
        cmd,
        cwd=str(ardupilot_home),
        env=env,
        stdout=stdout_target,
        stderr=stderr_target,
    )

    print(
        f"  Waiting for MAVLink data on UDP port {port} (timeout {SITL_STARTUP_TIMEOUT}s)..."
    )
    deadline = time.monotonic() + SITL_STARTUP_TIMEOUT
    server_ready = False

    while time.monotonic() < deadline:
        # Check if the SITL process died
        if process.poll() is not None:
            print(
                f"ERROR: SITL process exited prematurely (code {process.returncode}).\n"
                "Set SITL_VERBOSE=1 and retry to see SITL output.",
                file=sys.stderr,
            )
            sys.exit(1)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                # Bind to the port to catch the udpout packets from SITL
                s.bind(("0.0.0.0", port))
                # Set a 1-second timeout so we don't hang forever
                s.settimeout(1.0)

                # Attempt to read data. If SITL is running, it will be sending heartbeats.
                data, addr = s.recvfrom(1024)

                # If we get past recvfrom without a timeout, data has arrived!
                server_ready = True
                break

            except socket.timeout:
                # No data received within 1 second. Loop will repeat.
                pass
            except OSError:
                # If we actually DO get an OS error binding here, it means SITL
                # is using 'udpin' and bound the port itself. We can treat this as ready
                # (although this likely means QGC has the port and will crash farther down the line)
                server_ready = True
                break

    if not server_ready:
        process.terminate()
        print(
            f"ERROR: SITL failed to transmit data within {SITL_STARTUP_TIMEOUT}s.\n"
            "Set SITL_VERBOSE=1 and retry to see SITL output. This can happen\n"
            "if the SITL has not been built yet and it is attempting to build for the first time.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("  SITL is available to connect to.")


def stop_sitl(process: Optional[subprocess.Popen]) -> None:
    """Terminate SITL gracefully, kill if it doesn't stop in time."""
    if process is None or process.poll() is not None:
        return
    print("Stopping SITL...")
    # sim_vehicle.py starts processes in a new group if we aren't careful,
    # but here we just try to terminate the main script.
    # We use process_group to ensure all children (MAVProxy, ArduCopter) die.
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except OSError:
        process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except OSError:
            process.kill()


def main() -> None:
    """Parse CLI args, launch SITL, then run aerpawlib against that instance."""
    parser = argparse.ArgumentParser(
        description=(
            "Run an aerpawlib example script with a bundled SITL. "
            "Extra arguments are forwarded to aerpawlib."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  aerpawlib-run-example --script examples/v2/basic_example.py --vehicle drone\n"
            "  aerpawlib-run-example --script examples/v1/basic_example.py "
            "--vehicle drone --api-version v1\n"
            "  aerpawlib-run-example --script examples/v2/rover_example.py --vehicle rover\n"
            "\n"
            "Environment variables:\n"
            "  ARDUPILOT_HOME   Override path to ArduPilot directory\n"
            "  SITL_VERBOSE     Set to 1 to stream SITL output to the terminal\n"
        ),
    )
    parser.add_argument(
        "--script",
        required=True,
        metavar="PATH",
        help="Path to the example script (e.g. examples/v2/basic_example.py)",
    )
    parser.add_argument(
        "--vehicle",
        required=True,
        choices=["drone", "rover"],
        help="Vehicle type to simulate",
    )
    parser.add_argument(
        "--api-version",
        default="v2",
        choices=["v1", "v2"],
        dest="api_version",
        help="aerpawlib API version to use (default: v2)",
    )
    parser.add_argument(
        "--sitl-port",
        type=int,
        default=None,
        metavar="PORT",
        help=(
            "Override SITL UDP port "
            f"(default: {DEFAULT_PORT_DRONE} for drone, {DEFAULT_PORT_ROVER} for rover)"
        ),
    )
    parser.add_argument(
        "--speedup",
        type=int,
        default=5,
        metavar="N",
        help="SIM_SPEEDUP value for SITL (default: 5)",
    )

    args, extra_args = parser.parse_known_args()

    if args.vehicle == "drone":
        sitl_vehicle = "ArduCopter"
        default_port = DEFAULT_PORT_DRONE
        instance = DEFAULT_INSTANCE_DRONE
    else:
        sitl_vehicle = "Rover"
        default_port = DEFAULT_PORT_ROVER
        instance = DEFAULT_INSTANCE_ROVER

    port = args.sitl_port if args.sitl_port is not None else default_port
    conn_str = f"udpin://127.0.0.1:{port}"

    sitl_proc: Optional[subprocess.Popen] = None
    try:
        sitl_proc = start_sitl(sitl_vehicle, port, instance, args.speedup)

        aerpawlib_cmd = [
            sys.executable,
            "-m",
            "aerpawlib",
            "--script",
            args.script,
            "--vehicle",
            args.vehicle,
            "--conn",
            conn_str,
            "--api-version",
            args.api_version,
        ] + extra_args

        print("Running aerpawlib script...")
        print(f"  Running aerpawlib with command: {' '.join(aerpawlib_cmd)}\n")

        def _cleanup(signum=None, frame=None):
            print("\nInterrupted.")
            stop_sitl(sitl_proc)
            sys.exit(0)

        signal.signal(signal.SIGINT, _cleanup)
        signal.signal(signal.SIGTERM, _cleanup)

        result = subprocess.run(aerpawlib_cmd)
        result_code = result.returncode
    except Exception:
        # If start_sitl or command preparation fails, we still want to cleanup
        # although sitl_proc might be None
        result_code = 1
        raise
    finally:
        stop_sitl(sitl_proc)

    sys.exit(result_code)


if __name__ == "__main__":
    main()
