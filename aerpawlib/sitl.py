"""
SITL (Software In The Loop) management for aerpawlib.

This module provides utilities for starting and managing ArduPilot SITL
simulation instances for testing and development.

Supports:
- ArduPilot SITL with various vehicle types (copter, plane, rover)
- Multiple instances for multi-vehicle simulation
- QGroundControl connectivity
- Custom starting locations
- Simulation speedup

Usage:
    from aerpawlib.sitl import SITLManager, start_sitl

    # Quick start
    with start_sitl() as sitl:
        # sitl.connection_string contains the connection URI
        drone = Drone(sitl.connection_string)
        ...

    # Or manual management
    sitl = SITLManager(vehicle_type="copter")
    sitl.start()
    # ... do stuff ...
    sitl.stop()
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Any


class VehicleType(Enum):
    """ArduPilot vehicle types."""
    COPTER = "copter"
    PLANE = "plane"
    ROVER = "rover"
    SUB = "sub"
    HELICOPTER = "heli"
    QUADPLANE = "quadplane"


class SimulatorType(Enum):
    """Simulator backends for SITL."""
    NATIVE = "native"  # Built-in physics (no external sim)
    GAZEBO = "gazebo"
    AIRSIM = "airsim"
    XPLANE = "xplane"
    FLIGHTGEAR = "flightgear"


@dataclass
class SITLConfig:
    """Configuration for SITL instance."""
    vehicle_type: VehicleType = VehicleType.COPTER
    frame: Optional[str] = None  # e.g., "quad", "hexa", "+", "x"
    instance: int = 0
    speedup: float = 1.0
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    home_alt: Optional[float] = None
    home_heading: float = 0.0
    wipe_eeprom: bool = False
    model: Optional[str] = None  # Override vehicle model
    defaults_file: Optional[str] = None  # Custom parameter defaults
    extra_args: Optional[List[str]] = None


class SITLManager:
    """
    Manages ArduPilot SITL (Software In The Loop) simulation instances.

    Supports:
    - Starting ArduPilot SITL for various vehicle types
    - Multiple instances for multi-vehicle simulation
    - QGroundControl connectivity via UDP
    - Custom starting locations
    - Graceful shutdown

    Example:
        # Basic usage
        sitl = SITLManager()
        sitl.start()
        print(f"Connect to: {sitl.connection_string}")
        # ... run your mission ...
        sitl.stop()

        # With context manager
        with SITLManager(vehicle_type="copter") as sitl:
            drone = Drone(sitl.connection_string)
            await drone.connect()
            ...

        # Multi-vehicle
        sitl1 = SITLManager(instance=0)
        sitl2 = SITLManager(instance=1)
        sitl1.start()
        sitl2.start()
    """

    # Port configuration
    # ArduPilot SITL uses:
    # - 5760 + 10*instance: TCP MAVLink (for GCS)
    # - 5762 + 10*instance: TCP MAVLink (secondary)
    # - 14550 + instance: UDP MAVLink (for MAVSDK/pymavlink)
    BASE_MAVLINK_PORT = 5760
    BASE_UDP_PORT = 14550
    INSTANCE_PORT_OFFSET = 10

    def __init__(
        self,
        vehicle_type: str = "copter",
        frame: Optional[str] = None,
        instance: int = 0,
        speedup: float = 1.0,
        home: Optional[str] = None,
        home_lat: Optional[float] = None,
        home_lon: Optional[float] = None,
        home_alt: Optional[float] = None,
        home_heading: float = 0.0,
        wipe_eeprom: bool = False,
        model: Optional[str] = None,
        defaults_file: Optional[str] = None,
        ardupilot_path: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        console: bool = False,
        map_display: bool = False,
    ):
        """
        Initialize SITL manager.

        Args:
            vehicle_type: Vehicle type ('copter', 'plane', 'rover', 'sub')
            frame: Frame type (e.g., 'quad', 'hexa', '+', 'x', 'coaxcopter')
            instance: Instance number for multi-vehicle (0, 1, 2, ...)
            speedup: Simulation speedup factor (1.0 = realtime)
            home: Home location as "lat,lon,alt,heading" string
            home_lat: Home latitude (alternative to home string)
            home_lon: Home longitude (alternative to home string)
            home_alt: Home altitude in meters AMSL
            home_heading: Home heading in degrees
            wipe_eeprom: Wipe EEPROM/parameters on start
            model: Override vehicle model
            defaults_file: Path to custom parameter defaults file
            ardupilot_path: Path to ArduPilot source (auto-detected if not provided)
            extra_args: Additional arguments to pass to sim_vehicle.py
            console: Open MAVProxy console window
            map_display: Open MAVProxy map display
        """
        self.vehicle_type = vehicle_type.lower()
        self.frame = frame
        self.instance = instance
        self.speedup = speedup
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt = home_alt if home_alt is not None else 0.0
        self.home_heading = home_heading
        self.home = home
        self.wipe_eeprom = wipe_eeprom
        self.model = model
        self.defaults_file = defaults_file
        self.ardupilot_path = ardupilot_path or self._find_ardupilot_path()
        self.extra_args = extra_args or []
        self.console = console
        self.map_display = map_display

        self._process: Optional[subprocess.Popen] = None
        self._started = False
        self._venv_path: Optional[str] = None

    def _find_ardupilot_path(self) -> Optional[str]:
        """Try to find ArduPilot installation."""
        # Check environment variable first
        if os.environ.get("ARDUPILOT_HOME"):
            path = os.environ["ARDUPILOT_HOME"]
            if os.path.exists(os.path.join(path, "Tools", "autotest")):
                return path

        # Check project-local /ardupilot directory first (installed by install_ardupilot.sh)
        # This file is at aerpawlib/sitl.py, so project root is parent of aerpawlib
        this_file = os.path.abspath(__file__)
        aerpawlib_dir = os.path.dirname(this_file)
        project_root = os.path.dirname(aerpawlib_dir)
        project_ardupilot = os.path.join(project_root, "ardupilot")

        if os.path.exists(os.path.join(project_ardupilot, "Tools", "autotest")):
            return project_ardupilot

        # Check common locations
        common_paths = [
            os.path.expanduser("~/ardupilot"),
            os.path.expanduser("~/ArduPilot"),
            "/opt/ardupilot",
            os.path.expanduser("~/src/ardupilot"),
        ]

        for path in common_paths:
            if os.path.exists(os.path.join(path, "Tools", "autotest")):
                return path

        return None

    def _find_ardupilot_venv(self) -> Optional[str]:
        """Find the ArduPilot virtual environment."""
        # Check project-local /ardupilot-venv directory first (created by install_ardupilot.sh)
        this_file = os.path.abspath(__file__)
        aerpawlib_dir = os.path.dirname(this_file)
        project_root = os.path.dirname(aerpawlib_dir)
        project_venv = os.path.join(project_root, "ardupilot-venv")

        if os.path.exists(os.path.join(project_venv, "bin", "python")):
            return project_venv

        # Check next to ardupilot installation
        if self.ardupilot_path:
            parent = os.path.dirname(self.ardupilot_path)
            venv_path = os.path.join(parent, "ardupilot-venv")
            if os.path.exists(os.path.join(venv_path, "bin", "python")):
                return venv_path

        return None

    def _get_venv_python(self) -> str:
        """Get the Python executable from the ArduPilot venv, or system python."""
        if self._venv_path is None:
            self._venv_path = self._find_ardupilot_venv()

        if self._venv_path:
            venv_python = os.path.join(self._venv_path, "bin", "python")
            if os.path.exists(venv_python):
                return venv_python

        # Fall back to system python
        return sys.executable

    def _find_sim_vehicle(self) -> Optional[str]:
        """Find sim_vehicle.py script."""
        # Check if sim_vehicle.py is in PATH
        sim_vehicle = shutil.which("sim_vehicle.py")
        if sim_vehicle:
            return sim_vehicle

        # Check ArduPilot path
        if self.ardupilot_path:
            sim_vehicle = os.path.join(
                self.ardupilot_path, "Tools", "autotest", "sim_vehicle.py"
            )
            if os.path.exists(sim_vehicle):
                return sim_vehicle

        return None

    @property
    def tcp_port(self) -> int:
        """Get TCP MAVLink port for this instance."""
        return self.BASE_MAVLINK_PORT + (self.INSTANCE_PORT_OFFSET * self.instance)

    @property
    def udp_port(self) -> int:
        """Get UDP port for this instance (for MAVSDK connection)."""
        return self.BASE_UDP_PORT + self.instance

    @property
    def connection_string(self) -> str:
        """Get conne
        ction string for this SITL instance (for MAVSDK)."""
        return f"udpin://127.0.0.1:{self.udp_port}"

    @property
    def tcp_connection_string(self) -> str:
        """Get TCP connection string (for pymavlink/MAVProxy)."""
        return f"tcp:127.0.0.1:{self.tcp_port}"

    @property
    def is_running(self) -> bool:
        """Check if SITL is running."""
        return self._process is not None and self._process.poll() is None

    def _build_home_string(self) -> Optional[str]:
        """Build home location string."""
        if self.home:
            return self.home

        if self.home_lat is not None and self.home_lon is not None:
            return f"{self.home_lat},{self.home_lon},{self.home_alt},{self.home_heading}"

        return None

    def _build_command(self) -> List[str]:
        """Build the sim_vehicle.py command."""
        sim_vehicle = self._find_sim_vehicle()
        if not sim_vehicle:
            raise RuntimeError(
                "ArduPilot SITL not found. Please install ArduPilot using:\n"
                "  ./aerpawlib/install_ardupilot.sh\n"
                "\n"
                "Or set ARDUPILOT_HOME environment variable to your ArduPilot installation.\n"
                "See: https://ardupilot.org/dev/docs/building-setup-linux.html"
            )

        # Use the ArduPilot venv Python if available
        python_exe = self._get_venv_python()
        cmd = [python_exe, sim_vehicle]

        # Vehicle type
        cmd.extend(["-v", self.vehicle_type])

        # Frame
        if self.frame:
            cmd.extend(["-f", self.frame])

        # Instance
        if self.instance > 0:
            cmd.extend(["-I", str(self.instance)])

        # Speedup
        if self.speedup != 1.0:
            cmd.extend(["--speedup", str(self.speedup)])

        # Home location
        home = self._build_home_string()
        if home:
            cmd.extend(["-L", home])

        # Wipe EEPROM
        if self.wipe_eeprom:
            cmd.append("-w")

        # Model override
        if self.model:
            cmd.extend(["--model", self.model])

        # Defaults file
        if self.defaults_file:
            cmd.extend(["--add-param-file", self.defaults_file])

        # Console and map - use MAVProxy by default
        if self.console:
            cmd.append("--console")

        if self.map_display:
            cmd.append("--map")

        # Output for MAVSDK/pymavlink - MAVProxy will forward to this UDP address
        # Using udpout format for explicit output direction
        cmd.extend(["--out", f"udpout:127.0.0.1:{self.udp_port}"])

        # Extra arguments
        cmd.extend(self.extra_args)

        return cmd

    def start(self, timeout: float = 120.0) -> str:
        """
        Start the SITL instance.

        Args:
            timeout: Maximum time to wait for SITL to start (seconds)

        Returns:
            Connection string for the SITL instance

        Raises:
            RuntimeError: If SITL fails to start
        """
        if self._started:
            print(f"[aerpawlib] SITL instance {self.instance} already running")
            return self.connection_string

        print(f"[aerpawlib] Starting ArduPilot SITL...")
        print(f"[aerpawlib]   Vehicle: {self.vehicle_type}")
        if self.frame:
            print(f"[aerpawlib]   Frame: {self.frame}")
        print(f"[aerpawlib]   Instance: {self.instance}")
        print(f"[aerpawlib]   Speedup: {self.speedup}x")
        print(f"[aerpawlib]   UDP Port: {self.udp_port}")
        print(f"[aerpawlib]   TCP Port: {self.tcp_port}")

        # Log venv usage
        venv_path = self._find_ardupilot_venv()
        if venv_path:
            print(f"[aerpawlib]   Using venv: {venv_path}")
        else:
            print(f"[aerpawlib]   Using system Python: {sys.executable}")

        home = self._build_home_string()
        if home:
            print(f"[aerpawlib]   Home: {home}")

        cmd = self._build_command()
        print(f"[aerpawlib]   Command: {' '.join(cmd)}")

        # Start the process
        env = os.environ.copy()

        # Ensure ArduPilot paths are set
        if self.ardupilot_path:
            env["ARDUPILOT_HOME"] = self.ardupilot_path

        verbose = os.environ.get("SITL_VERBOSE", "0") == "1"

        self._process = subprocess.Popen(
            cmd,
            cwd=self.ardupilot_path or os.getcwd(),
            env=env,
            stdout=None if verbose else subprocess.DEVNULL,
            stderr=None if verbose else subprocess.DEVNULL,
            preexec_fn=os.setsid if sys.platform != "win32" else None,
        )

        # Wait for SITL to be ready
        self._wait_for_sitl(timeout)
        self._started = True

        print(f"[aerpawlib] SITL ready!")
        print(f"[aerpawlib]   MAVSDK connection: {self.connection_string}")
        print(f"[aerpawlib]   TCP connection: {self.tcp_connection_string}")
        print(f"[aerpawlib] ------------------------------------------------")
        print(f"[aerpawlib] QGroundControl: Connect via TCP to localhost:{self.tcp_port}")
        print(f"[aerpawlib]   In QGC: Application Settings > Comm Links > Add")
        print(f"[aerpawlib]   Type: TCP, Host: localhost, Port: {self.tcp_port}")
        print(f"[aerpawlib] ------------------------------------------------")

        return self.connection_string

    def _wait_for_sitl(self, timeout: float = 120.0) -> None:
        """Wait for SITL to be ready to accept connections."""
        print("[aerpawlib] Waiting for SITL to initialize...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if process crashed
            if self._process and self._process.poll() is not None:
                raise RuntimeError(
                    f"SITL process terminated unexpectedly with code {self._process.returncode}"
                )

            # Try to connect to the TCP port
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                result = sock.connect_ex(("127.0.0.1", self.tcp_port))
                sock.close()

                if result == 0:
                    # Connection successful, give it a moment to stabilize
                    time.sleep(3)
                    return

            except socket.error:
                pass

            time.sleep(1)

        raise RuntimeError(f"SITL failed to start within {timeout} seconds")

    def stop(self) -> None:
        """Stop the SITL instance."""
        if self._process is None:
            return

        print(f"[aerpawlib] Stopping SITL instance {self.instance}...")

        try:
            if sys.platform != "win32":
                # Send SIGTERM to the process group
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            else:
                self._process.terminate()

            # Wait for graceful shutdown
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                else:
                    self._process.kill()
                self._process.wait()

        except (ProcessLookupError, OSError):
            pass  # Process already terminated

        self._process = None
        self._started = False
        print("[aerpawlib] SITL stopped")

    def check_alive(self) -> None:
        """
        Check if SITL is still alive, raising an exception if it has terminated.

        Raises:
            RuntimeError: If SITL process has terminated unexpectedly.
        """
        if self._process is None:
            raise RuntimeError("SITL was never started")

        return_code = self._process.poll()
        if return_code is not None:
            self._started = False
            raise RuntimeError(
                f"SITL process terminated unexpectedly with code {return_code}"
            )

    def get_return_code(self) -> Optional[int]:
        """
        Get the return code of the SITL process if it has terminated.

        Returns:
            Return code if process has terminated, None if still running.
        """
        if self._process is None:
            return None

        return self._process.poll()

    def wait_for_termination(self, timeout: Optional[float] = None) -> int:
        """
        Wait for the SITL process to terminate.

        Args:
            timeout: Maximum time to wait (seconds). None means wait indefinitely.

        Returns:
            Process return code.

        Raises:
            RuntimeError: If SITL was never started.
            subprocess.TimeoutExpired: If timeout is reached.
        """
        if self._process is None:
            raise RuntimeError("SITL was never started")

        return_code = self._process.wait(timeout=timeout)
        self._started = False
        return return_code

    def __enter__(self) -> "SITLManager":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        self.stop()
        return False


def start_sitl(
    vehicle_type: str = "copter",
    frame: Optional[str] = None,
    instance: int = 0,
    speedup: float = 1.0,
    home_lat: Optional[float] = None,
    home_lon: Optional[float] = None,
    home_alt: Optional[float] = None,
    **kwargs: Any,
) -> SITLManager:
    """
    Start a SITL instance (convenience function).

    Args:
        vehicle_type: Vehicle type ('copter', 'plane', 'rover')
        frame: Frame type (e.g., 'quad', 'hexa')
        instance: Instance number for multi-vehicle
        speedup: Simulation speedup factor
        home_lat: Starting latitude
        home_lon: Starting longitude
        home_alt: Starting altitude
        **kwargs: Additional arguments passed to SITLManager

    Returns:
        Started SITLManager instance

    Example:
        sitl = start_sitl(vehicle_type="copter", speedup=2)
        drone = Drone(sitl.connection_string)
        # ... do stuff ...
        sitl.stop()
    """
    manager = SITLManager(
        vehicle_type=vehicle_type,
        frame=frame,
        instance=instance,
        speedup=speedup,
        home_lat=home_lat,
        home_lon=home_lon,
        home_alt=home_alt,
        **kwargs,
    )
    manager.start()
    return manager


class MultiSITL:
    """
    Manager for multiple SITL instances (swarm simulation).

    Example:
        with MultiSITL(count=3) as swarm:
            for sitl in swarm.instances:
                drone = Drone(sitl.connection_string)
                # ...
    """

    def __init__(
        self,
        count: int = 2,
        vehicle_type: str = "copter",
        spacing: float = 5.0,
        home_lat: float = 35.7749,
        home_lon: float = -78.6419,
        home_alt: float = 0.0,
        speedup: float = 1.0,
        **kwargs: Any,
    ):
        """
        Initialize multi-SITL manager.

        Args:
            count: Number of SITL instances
            vehicle_type: Vehicle type for all instances
            spacing: Spacing between vehicles in meters (east-west)
            home_lat: Base latitude for first vehicle
            home_lon: Base longitude for first vehicle
            home_alt: Home altitude for all vehicles
            speedup: Simulation speedup
            **kwargs: Additional args passed to each SITLManager
        """
        self.count = count
        self.vehicle_type = vehicle_type
        self.spacing = spacing
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt = home_alt
        self.speedup = speedup
        self.kwargs = kwargs

        self.instances: List[SITLManager] = []

    def _offset_longitude(self, base_lon: float, meters_east: float, lat: float) -> float:
        """Calculate longitude offset for given meters east."""
        import math
        # Approximate meters per degree longitude at given latitude
        # TODO: More accurate calculation could be used if needed
        meters_per_deg = 111320 * math.cos(math.radians(lat))
        return base_lon + (meters_east / meters_per_deg)

    def start(self) -> List[str]:
        """
        Start all SITL instances.

        Returns:
            List of connection strings for all instances
        """
        print(f"[aerpawlib] Starting {self.count} SITL instances...")

        connection_strings = []

        for i in range(self.count):
            # Calculate offset position
            lon = self._offset_longitude(self.home_lon, i * self.spacing, self.home_lat)

            sitl = SITLManager(
                vehicle_type=self.vehicle_type,
                instance=i,
                speedup=self.speedup,
                home_lat=self.home_lat,
                home_lon=lon,
                home_alt=self.home_alt,
                **self.kwargs,
            )

            sitl.start()
            self.instances.append(sitl)
            connection_strings.append(sitl.connection_string)

        print(f"[aerpawlib] All {self.count} SITL instances started")
        return connection_strings

    def stop(self) -> None:
        """Stop all SITL instances."""
        print(f"[aerpawlib] Stopping {len(self.instances)} SITL instances...")

        for sitl in self.instances:
            sitl.stop()

        self.instances.clear()
        print("[aerpawlib] All SITL instances stopped")

    def __enter__(self) -> "MultiSITL":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        self.stop()
        return False


# Export public API
__all__ = [
    "SITLManager",
    "SITLConfig",
    "VehicleType",
    "SimulatorType",
    "MultiSITL",
    "start_sitl",
]

