"""
Tool used to run aerpawlib scripts that make use of a Runner class.

usage:
    python -m aerpawlib --script <script import path> --conn <connection string> \
            --vehicle <vehicle type>

example:
    python -m aerpawlib --script experimenter_script --conn /dev/ttyACM0 \
            --vehicle drone

With SITL (ArduPilot):
    # First, install ArduPilot SITL (one-time setup)
    python -m aerpawlib --sitl-install

    # Then run with SITL
    python -m aerpawlib --script experimenter_script --vehicle drone --sitl
    python -m aerpawlib --script experimenter_script --vehicle drone --sitl --sitl-speedup 2

    # With MAVProxy console and map
    python -m aerpawlib --script experimenter_script --vehicle drone --sitl --sitl-console --sitl-map
"""

# Removed static imports so we can select API version at runtime
# (the appropriate modules will be imported after parsing CLI args)

import asyncio
import importlib
import inspect
import os
import signal
import sys
import time
from argparse import ArgumentParser
from typing import Optional
import subprocess
# Import SITL management from helper module
from aerpawlib.sitl import SITLManager


def main():
    """Main entry point for aerpawlib CLI."""

    # Import trick to allow things to work when run as "aerpawlib"

    current_file = os.path.abspath(__file__)

    # 2. Go up two levels to find the Project Root
    #    Level 1: /.../aerpawlib-vehicle-control/aerpawlib
    #    Level 2: /.../aerpawlib-vehicle-control (Where 'examples' lives)
    project_root = os.path.dirname(os.path.dirname(current_file))

    # 3. Set the Process CWD to the Project Root
    #    (This does NOT change your terminal's path, only this running process)
    os.chdir(project_root)
    sys.path.insert(0, os.getcwd())

    proxy_mode = "--run-proxy" in sys.argv
    sitl_mode = "--sitl" in sys.argv

    parser = ArgumentParser(description="aerpawlib - wrap and run aerpaw scripts")
    parser.add_argument("--script", help="experimenter script", required=not proxy_mode)
    parser.add_argument("--conn", help="connection string (auto-set when using --sitl)",
                        required=not (proxy_mode or sitl_mode))
    parser.add_argument("--vehicle", help="vehicle type [generic, drone, rover, none]", required=not proxy_mode)
    parser.add_argument("--api-version", help="which API version to use (v1 or v2)",
                        choices=["v1", "v2"], default="v1")
    parser.add_argument("--skip-init", help="skip initialization", required=False,
            const=False, default=True, action="store_const", dest="initialize")
    parser.add_argument("--run-proxy", help="run zmq proxy", required=False,
            const=True, default=False, action="store_const", dest="run_zmq_proxy")
    parser.add_argument("--zmq-identifier", help="zmq identifier", required=False, dest="zmq_identifier")
    parser.add_argument("--zmq-proxy-server", help="zmq proxy server addr", required=False, dest="zmq_server_addr")
    parser.add_argument("--skip-rtl", help="don't rtl and land at the end of an experiment automatically",
            const=False, default=True, action="store_const", dest="rtl_at_end")
    parser.add_argument("--debug-dump", help="run aerpawlib's internal debug dump on vehicle object", required=False,
            const=True, default=False, action="store_const", dest="debug_dump")
    parser.add_argument("--no-aerpawlib-stdout", help="prevent aerpawlib from printing to stdout", required=False,
            const=True, default=False, action="store_const", dest="no_stdout")

    # SITL arguments (ArduPilot)
    parser.add_argument("--sitl", help="start ArduPilot SITL simulator before running script",
            action="store_true", default=False)
    parser.add_argument("--sitl-install", help="install ArduPilot SITL to project /ardupilot directory",
            action="store_true", default=False, dest="sitl_install")
    parser.add_argument("--sitl-speedup", help="SITL simulation speedup factor (default: 1.0)",
            type=float, default=1.0, dest="sitl_speedup")
    parser.add_argument("--sitl-vehicle", help="vehicle type for SITL [copter, plane, rover, sub]",
            choices=["copter", "plane", "rover", "sub"], default="copter", dest="sitl_vehicle")
    parser.add_argument("--sitl-frame", help="frame type for SITL (e.g., quad, hexa, +, x)",
            default=None, dest="sitl_frame")
    parser.add_argument("--sitl-instance", help="SITL instance number for multi-vehicle simulation",
            type=int, default=0, dest="sitl_instance")
    parser.add_argument("--sitl-home", help="SITL home location as 'lat,lon,alt,heading'",
            default=None, dest="sitl_home")
    parser.add_argument("--sitl-lat", help="SITL starting latitude",
            type=float, default=None, dest="sitl_lat")
    parser.add_argument("--sitl-lon", help="SITL starting longitude",
            type=float, default=None, dest="sitl_lon")
    parser.add_argument("--sitl-alt", help="SITL starting altitude (AMSL)",
            type=float, default=None, dest="sitl_alt")
    parser.add_argument("--sitl-wipe", help="wipe EEPROM/parameters on start",
            action="store_true", default=False, dest="sitl_wipe")
    parser.add_argument("--sitl-console", help="open MAVProxy console window",
            action="store_true", default=False, dest="sitl_console")
    parser.add_argument("--sitl-map", help="open MAVProxy map display",
            action="store_true", default=False, dest="sitl_map")
    parser.add_argument("--sitl-ardupilot-path", help="path to ArduPilot directory",
            default=None, dest="sitl_ardupilot_path")
    parser.add_argument("--sitl-verbose", help="show SITL output in console",
            action="store_true", default=False, dest="sitl_verbose")

    args, unknown_args = parser.parse_known_args() # we'll pass other args to the script

    # Handle --sitl-install: run the install script and exit
    if args.sitl_install:
        # Find the install script relative to this file
        this_file = os.path.abspath(__file__)
        aerpawlib_dir = os.path.dirname(this_file)
        install_script = os.path.join(aerpawlib_dir, "install_ardupilot.sh")

        if not os.path.exists(install_script):
            print(f"[aerpawlib] ERROR: Install script not found at {install_script}")
            sys.exit(1)

        print("[aerpawlib] Running ArduPilot SITL installer...")
        # Pass through vehicle type to installer
        install_args = [install_script, "--vehicle", args.sitl_vehicle]
        result = subprocess.run(["bash"] + install_args)
        sys.exit(result.returncode)

    # SITL manager instance (will be set if --sitl is used)
    sitl_manager: Optional[SITLManager] = None

    # Helper function to check if ArduPilot is installed and offer to install
    def check_and_install_ardupilot(vehicle_type: str) -> bool:
        """Check if ArduPilot is installed, offer to install if not. Returns True if available."""
        this_file = os.path.abspath(__file__)
        aerpawlib_dir = os.path.dirname(this_file)
        project_root = os.path.dirname(aerpawlib_dir)
        ardupilot_dir = os.path.join(project_root, "ardupilot")
        venv_dir = os.path.join(project_root, "ardupilot-venv")
        sim_vehicle_path = os.path.join(ardupilot_dir, "Tools", "autotest", "sim_vehicle.py")

        # Check if already installed in project directory
        if os.path.exists(sim_vehicle_path):
            return True

        # Check ARDUPILOT_HOME
        if os.environ.get("ARDUPILOT_HOME"):
            env_path = os.path.join(os.environ["ARDUPILOT_HOME"], "Tools", "autotest", "sim_vehicle.py")
            if os.path.exists(env_path):
                return True

        # Check common locations
        for path in ["~/ardupilot", "~/ArduPilot", "/opt/ardupilot"]:
            expanded = os.path.expanduser(path)
            if os.path.exists(os.path.join(expanded, "Tools", "autotest", "sim_vehicle.py")):
                return True

        # Not found - prompt to install
        print("[aerpawlib] ================================================")
        print("[aerpawlib] ArduPilot SITL not found!")
        print("[aerpawlib] ================================================")
        print("")
        print(f"[aerpawlib] ArduPilot will be installed to: {ardupilot_dir}")
        print(f"[aerpawlib] Python venv will be created at: {venv_dir}")
        print("[aerpawlib] This may take 10-30 minutes depending on your system.")
        print("")

        try:
            response = input("[aerpawlib] Install ArduPilot now? [Y/n]: ").strip().lower()
        except EOFError:
            response = "n"

        if response in ("", "y", "yes"):
            install_script = os.path.join(aerpawlib_dir, "install_ardupilot.sh")
            if not os.path.exists(install_script):
                print(f"[aerpawlib] ERROR: Install script not found at {install_script}")
                return False

            print("")
            print("[aerpawlib] Starting ArduPilot installation...")
            print("")

            install_args = [install_script, "--vehicle", vehicle_type]
            result = subprocess.run(["bash"] + install_args)

            if result.returncode != 0:
                print("[aerpawlib] ERROR: ArduPilot installation failed.")
                return False

            return True
        else:
            print("")
            print("[aerpawlib] To install ArduPilot manually, run:")
            print(f"  ./aerpawlib/install_ardupilot.sh")
            print("")
            print("[aerpawlib] Or set ARDUPILOT_HOME to your existing ArduPilot installation.")
            return False

    # Handle SITL startup
    if args.sitl:
        if args.sitl_verbose:
            os.environ["SITL_VERBOSE"] = "1"

        # Check if ArduPilot is installed, offer to install if not
        if not check_and_install_ardupilot(args.sitl_vehicle):
            print("[aerpawlib] Cannot start SITL without ArduPilot. Exiting.")
            sys.exit(1)

        print("[aerpawlib] ================================================")
        print("[aerpawlib] Starting ArduPilot SITL Simulator")
        print("[aerpawlib] ================================================")

        sitl_manager = SITLManager(
            vehicle_type=args.sitl_vehicle,
            frame=args.sitl_frame,
            instance=args.sitl_instance,
            speedup=args.sitl_speedup,
            home=args.sitl_home,
            home_lat=args.sitl_lat,
            home_lon=args.sitl_lon,
            home_alt=args.sitl_alt,
            wipe_eeprom=args.sitl_wipe,
            ardupilot_path=args.sitl_ardupilot_path,
            console=args.sitl_console,
            map_display=args.sitl_map,
        )

        try:
            conn_string = sitl_manager.start()
            # Override connection string with SITL connection
            args.conn = conn_string
        except Exception as e:
            print(f"[aerpawlib] Failed to start SITL: {e}")
            sys.exit(1)

        # Register signal handlers to clean up SITL on exit
        def cleanup_sitl(signum, frame):
            if sitl_manager:
                sitl_manager.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, cleanup_sitl)
        signal.signal(signal.SIGTERM, cleanup_sitl)

    # Dynamically import all symbols from the selected API version into global namespace
    api_version = args.api_version
    try:
        api_module = importlib.import_module(f"aerpawlib.{api_version}")
        # Import all public symbols from the API module into globals
        if hasattr(api_module, '__all__'):
            for name in api_module.__all__:
                globals()[name] = getattr(api_module, name)
        else:
            # If no __all__ is defined, import all non-private symbols
            for name in dir(api_module):
                if not name.startswith('_'):
                    globals()[name] = getattr(api_module, name)
    except Exception as e:
        raise Exception(f"Failed to import aerpawlib {api_version}: {e}")

    if args.run_zmq_proxy:
        # don't even bother running the script, just the proxy
        globals()['run_zmq_proxy']()
        exit()

    # import script and use reflection to get StateMachine
    experimenter_script = importlib.import_module(args.script)

    runner = None
    flag_zmq_runner = False
    Runner = globals()['Runner']
    StateMachine = globals()['StateMachine']
    BasicRunner = globals()['BasicRunner']
    ZmqStateMachine = globals()['ZmqStateMachine']

    for _, val in inspect.getmembers(experimenter_script):
        if not inspect.isclass(val):
            continue
        if not issubclass(val, Runner):
            continue
        if val in [StateMachine, BasicRunner, ZmqStateMachine]:
            continue
        if issubclass(val, ZmqStateMachine):
            flag_zmq_runner = True
        if runner:
            raise Exception("You can only define one runner")
        runner = val()

    Vehicle = globals()['Vehicle']
    Drone = globals()['Drone']
    Rover = globals()['Rover']
    DummyVehicle = globals()['DummyVehicle']
    AERPAW_Platform = globals()['AERPAW_Platform']

    vehicle_type = {
            "generic": Vehicle,
            "drone": Drone,
            "rover": Rover,
            "none": DummyVehicle
            }.get(args.vehicle, None)
    if vehicle_type is None:
        raise Exception("Please specify a valid vehicle type")
    vehicle = vehicle_type(args.conn)
    
    if args.debug_dump and hasattr(vehicle, "_verbose_logging"):
        vehicle._verbose_logging = True

    AERPAW_Platform._no_stdout = args.no_stdout

    # everything after this point is user script dependent. avoid adding extra logic below here

    runner.initialize_args(unknown_args)
    
    if vehicle_type in [Drone, Rover] and args.initialize:
        vehicle._initialize_prearm(args.initialize)

    if flag_zmq_runner:
        if None in [args.zmq_identifier, args.zmq_server_addr]:
            raise Exception("you must declare an identifier and server address for a zmq enabled state machine")
        print("[aerpawlib] initializing zmq bindings")
        runner._initialize_zmq_bindings(args.zmq_identifier, args.zmq_server_addr)

    asyncio.run(runner.run(vehicle))
    
    # rtl / land if not already done
    async def _rtl_cleanup(vehicle):
        await vehicle.goto_coordinates(vehicle._home_location)
        if vehicle_type in [Drone]:
            await vehicle.land()

    if vehicle_type in [Drone, Rover]:
        if vehicle.armed and args.rtl_at_end:
            AERPAW_Platform.log_to_oeo("[aerpawlib] Vehicle still armed after experiment! RTLing and LANDing automatically.")
            asyncio.run(_rtl_cleanup(vehicle))

        stop_time = time.time()
        seconds_to_complete = int(stop_time - vehicle._mission_start_time)
        time_to_complete = f"{(seconds_to_complete // 60):02d}:{(seconds_to_complete % 60):02d}"
        AERPAW_Platform.log_to_oeo(f"[aerpawlib] Mission took {time_to_complete} mm:ss")

    # clean up
    vehicle.close()

    # Stop SITL if it was started
    if sitl_manager is not None:
        sitl_manager.stop()


if __name__ == "__main__":
    main()


