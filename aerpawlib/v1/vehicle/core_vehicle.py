"""
Core vehicle infrastructure for the v1 API.

This module implements the shared MAVSDK-backed base behavior used by v1
vehicle types, including connection lifecycle, telemetry synchronization,
thread bridging, and safety-oriented initialization.

Capabilities:
- Manage dual-loop execution between runner code and MAVSDK operations.
- Track telemetry through thread-safe wrappers and background subscriptions.
- Provide shared preflight, arming, and shutdown behavior for vehicles.

Notes:
- Concrete movement behavior is implemented by `Drone` and `Rover` modules on
  top of this shared base implementation.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from grpc.aio import AioRpcError
from mavsdk import System
from mavsdk.action import ActionError

from aerpawlib.v1 import util
from aerpawlib.v1.aerpaw import AERPAW_Platform
from aerpawlib.v1.constants import (
    ARMABLE_STATUS_LOG_INTERVAL_S,
    ARMABLE_TIMEOUT_S,
    ARMING_SEQUENCE_DELAY_S,
    CONNECTION_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
    GPS_3D_FIX_TYPE,
    INTERNAL_UPDATE_DELAY_S,
    MAVSDK_THREAD_SHUTDOWN_TIMEOUT_S,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
    STRUCTURED_TELEMETRY_INTERVAL_S,
    VERBOSE_LOG_DELAY_S,
    VERBOSE_LOG_FILE_PREFIX,
)
from aerpawlib.v1.exceptions import (
    AerpawConnectionError,
    ArmError,
    ConnectionTimeoutError,
    DisarmError,
    NotArmableError,
    NotImplementedForVehicleError,
    PortInUseError,
)
from aerpawlib.v1.helpers import (
    wait_for_condition,
)
from aerpawlib.v1.log import LogComponent, get_logger
from aerpawlib.v1.util import is_tcp_port_in_use, is_udp_port_in_use

from . import telemetry_subscriptions
from .connection import _parse_udp_connection_port
from .connection_lifecycle import ConnectionLifecycle
from .state import InitPhase, ThreadSafeVehicleState
from .telemetry_compat import (
    _AttitudeCompat,
    _BatteryCompat,
    _GPSInfoCompat,
    _VersionCompat,
)

# Named timeouts (L4/L5)
_MAVSDK_LOOP_TIMEOUT_S = 30.0
_HOME_WAIT_TIMEOUT_S = 5.0

# Configure module logger
logger = get_logger(LogComponent.VEHICLE)


class Vehicle:
    """
    Overarching "generic vehicle" type.

    Implements common functionality for all vehicle types (drone, rover, etc.),
    excluding specific movement commands. This class maintains an internal
    MAVSDK session while providing a DroneKit-compatible API.

    Internal state map:
    - ``_lifecycle`` (ConnectionLifecycle): heartbeat, closed, running
    - ``_ts_state`` (ThreadSafeVehicleState): telemetry behind public properties
    - ``_init_phase``: arm/init sequence (InitPhase enum)
    """

    _system: System | None
    _ready_to_move: Callable[[Vehicle], bool]
    _abortable: bool
    _aborted: bool
    _current_heading: float | None
    _last_nav_controller_output: Any | None
    _last_mission_item_int: Any | None
    _verbose_logging: bool
    _verbose_logging_file_prefix: str
    _verbose_logging_file_path: Path | None
    _verbose_logging_last_log_time: float
    _verbose_logging_delay: float
    _verbose_log_lock: threading.Lock
    _event_log: Any | None
    _structured_telemetry_last_log_time: float
    _skip_init: bool
    _skip_rtl: bool

    def __init__(self, connection_string: str, mavsdk_server_port: int = 50051) -> None:
        """
        Initialize the vehicle and connect to the autopilot.

        Args:
            connection_string: MAVLink connection string (e.g., 'udp://:14540').
            mavsdk_server_port: Port for the embedded mavsdk_server gRPC interface.
                Each Vehicle instance should use a unique port to avoid conflicts.
                Defaults to 50051.

        Raises:
            ConnectionTimeoutError: If connection cannot be established within timeout.
        """
        self._connection_string = connection_string
        self._mavsdk_server_port = mavsdk_server_port
        self._system = None
        self._lifecycle = ConnectionLifecycle()
        self._connection_error: BaseException | None = None
        self._ready_to_move = lambda _: True
        self._abortable = False
        self._aborted = False
        self._current_heading = None
        self._last_nav_controller_output = None
        self._last_mission_item_int = None
        self._verbose_logging = False
        self._verbose_logging_file_prefix = VERBOSE_LOG_FILE_PREFIX
        self._verbose_logging_file_path = None
        self._verbose_logging_last_log_time = 0.0
        self._verbose_logging_delay = VERBOSE_LOG_DELAY_S
        self._verbose_log_lock = threading.Lock()
        self._event_log = None
        self._structured_telemetry_last_log_time = 0.0
        self._will_arm = True
        self._mission_start_time: float | None = None

        self._skip_init = False
        self._skip_rtl = False
        self._init_phase = InitPhase.PENDING
        self._ts_state = ThreadSafeVehicleState()
        self._autopilot_info = _VersionCompat()

        # Track active futures for cancellation in close()
        self._pending_mavsdk_futures = set()
        self._pending_mavsdk_lock = threading.Lock()

        # Telemetry and command tasks
        self._telemetry_tasks: list[asyncio.Task] = []
        self._command_tasks: list[asyncio.Task] = []

        # Event loop for MAVSDK operations (runs in background thread)
        self._mavsdk_loop: asyncio.AbstractEventLoop | None = None

        # Connect synchronously (blocking)
        self._connect_sync()

    def set_event_log(self, event_log: Any | None) -> None:
        """Attach structured JSONL logger from ``--structured-log`` (v1)."""
        self._event_log = event_log

    def _connect_sync(self) -> None:
        """
        Establish connection and start telemetry in background threads.

        This is a synchronous wrapper around asynchronous connection logic.
        """

        # Fail fast if UDP port from connection string is already in use
        # (avoids hanging)
        parsed = _parse_udp_connection_port(self._connection_string)
        if parsed is not None:
            host, port = parsed
            if is_udp_port_in_use(host, port):
                raise PortInUseError(
                    port,
                    f"UDP port {port} is already in use. Stop the other process or use a different connection string.",
                )

        # Warn if mavsdk gRPC port is already in use (avoids confusing
        # multi-vehicle issues)
        if is_tcp_port_in_use("127.0.0.1", self._mavsdk_server_port):
            # Previously this raised PortInUseError which caused an immediate crash.
            # Prefer a non-fatal warning so multiple vehicle processes can still
            # attempt to run (the gRPC server may still be usable or the caller
            # may prefer to continue). Keep PortInUseError for callers that want
            # a fail-fast behavior.

            # This behavior is because the test suite will trigger this failure case
            # and we still want to be able to run tests :P
            logger.warning(
                "MAVSDK gRPC port %d appears to be in use. Proceeding anyway. If running multiple vehicles, consider using --mavsdk-port with a unique port per process (e.g. --mavsdk-port 50051 for the first, --mavsdk-port 50052 for the second).",
                self._mavsdk_server_port,
            )

        loop = asyncio.new_event_loop()
        self._mavsdk_loop = loop  # Store reference for thread-safe calls

        def _run_connection() -> None:
            """Run the MAVSDK loop lifecycle inside the dedicated thread."""
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._connect_async())
                # Keep the loop running for telemetry
                loop.run_forever()
            except BaseException as e:
                self._connection_error = e
            finally:
                # Ensure all tasks are cancelled and loop is closed
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True),
                    )
                loop.close()

        # Start connection in background thread
        self._mavsdk_thread = threading.Thread(target=_run_connection, daemon=True)
        self._mavsdk_thread.start()

        # Wait for connection with timeout
        start = time.time()
        while not self._lifecycle.has_heartbeat:
            if self._connection_error is not None:
                err = self._connection_error
                self._connection_error = None
                if isinstance(err, AerpawConnectionError):
                    raise err
                raise AerpawConnectionError(
                    f"Connection failed: {err}",
                    original_error=err,
                )
            if time.time() - start > CONNECTION_TIMEOUT_S:
                raise ConnectionTimeoutError(CONNECTION_TIMEOUT_S)
            time.sleep(POLLING_DELAY_S)

        # Start internal update loop
        update_thread = threading.Thread(target=self._internal_update_loop, daemon=True)
        update_thread.start()

    async def _run_on_mavsdk_loop(self, coro: Any) -> Any:
        """
        Run a coroutine on the MAVSDK event loop.

        Args:
            coro: The coroutine to execute.

        Returns:
            The result of the coroutine.

        Raises:
            RuntimeError: If the MAVSDK loop is not initialized or not running.
        """
        if self._mavsdk_loop is None:
            raise RuntimeError("MAVSDK loop not initialized")
        if not self._mavsdk_loop.is_running():
            # If the loop isn't running yet, we might be in the middle of connecting
            # or it has crashed.
            logger.warning("MAVSDK loop is not yet running, waiting...")
            start_time = time.time()
            while not self._mavsdk_loop.is_running() and time.time() - start_time < 5.0:
                await asyncio.sleep(POLLING_DELAY_S)
            if not self._mavsdk_loop.is_running():
                raise RuntimeError("MAVSDK loop is not running")

        future = asyncio.run_coroutine_threadsafe(coro, self._mavsdk_loop)
        with self._pending_mavsdk_lock:
            # Track every submitted coroutine so close() can cancel in-flight
            # operations before shutting down the MAVSDK loop/thread.
            self._pending_mavsdk_futures.add(future)
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(future),
                timeout=_MAVSDK_LOOP_TIMEOUT_S,
            )
        except asyncio.TimeoutError as e:
            future.cancel()
            raise RuntimeError(
                f"MAVSDK operation timed out after {_MAVSDK_LOOP_TIMEOUT_S}s; the MAVSDK event loop may have crashed",
            ) from e
        except (AioRpcError, Exception) as e:
            if isinstance(e, AioRpcError):
                raise AerpawConnectionError(f"MAVSDK gRPC error: {e}") from e
            raise
        finally:
            with self._pending_mavsdk_lock:
                self._pending_mavsdk_futures.discard(future)

    async def _connect_async(self) -> None:
        """
        Asynchronously connect to the MAVSDK system and start telemetry tasks.
        """
        self._system = System(port=self._mavsdk_server_port)
        await asyncio.wait_for(
            self._system.connect(system_address=self._connection_string),
            timeout=CONNECTION_TIMEOUT_S,
        )

        # Wait for connection state with timeout; wrap in wait_for so the
        # async generator doesn't block forever on an invalid connection string.
        async def _wait_for_heartbeat() -> None:
            """Block until MAVSDK reports a connected vehicle state."""
            async for state in self._system.core.connection_state():
                if state.is_connected:
                    self._lifecycle.has_heartbeat = True
                    return

        try:
            await asyncio.wait_for(_wait_for_heartbeat(), timeout=CONNECTION_TIMEOUT_S)
        except asyncio.TimeoutError as e:
            raise ConnectionTimeoutError(
                CONNECTION_TIMEOUT_S,
                message=("Connection established but no heartbeat received within timeout"),
            ) from e

        await telemetry_subscriptions.start_telemetry(self)
        await telemetry_subscriptions.fetch_vehicle_info(self)

    # Properties - maintaining original API
    @property
    def connected(self) -> bool:
        """
        True if receiving heartbeats, False otherwise
        """
        return self._lifecycle.has_heartbeat

    @property
    def closed(self) -> bool:
        """
        True if the vehicle connection has been closed.
        """
        return self._lifecycle.closed

    @property
    def armable(self) -> bool:
        """
        True if the vehicle preflight checks pass and is ready to arm.
        """
        return self._ts_state.is_armable_state.get()

    @property
    def position(self) -> util.Coordinate:
        """
        Get the current position of the Vehicle as a `util.Coordinate`
        """
        return util.Coordinate(
            self._ts_state.position_lat.get(),
            self._ts_state.position_lon.get(),
            self._ts_state.position_alt.get(),
        )

    @property
    def home_amsl(self) -> float:
        """
        Get the absolute altitude (AMSL) of the home position in meters.

        Returns:
            float: Altitude Above Mean Sea Level.
        """
        return self._ts_state.home_abs_alt.get()

    @property
    def battery(self) -> _BatteryCompat:
        """
        Get the status of the battery. Returns object with `voltage`, `current`,
        and `level`.
        """
        return self._ts_state.battery_val.get()

    @property
    def gps(self) -> _GPSInfoCompat:
        """
        Get the current GPS status.
        Exposes the `fix_type` (0-1: no fix, 2: 2d fix, 3: 3d fix),
        and number of `satellites_visible`.
        """
        return self._ts_state.gps_val.get()

    @property
    def armed(self) -> bool:
        """
        True if the vehicle is currently armed.
        """
        return self._ts_state.armed_state.get()

    @property
    def ekf_ready(self) -> bool:
        """True if EKF reports ready for takeoff (ArduPilot)."""
        return self._ts_state.ekf_ready.get()

    @property
    def home_coords(self) -> util.Coordinate | None:
        """
        Get the home location from MAVLink telemetry.
        Returns the autopilot's home position, or falls back to _home_location if
        not available.
        """
        home = self._ts_state.home_position.get()
        if home is not None:
            return home
        return self._ts_state.captured_home.get()

    @property
    def heading(self) -> float:
        """Heading in degrees from telemetry."""
        return self._ts_state.heading_deg.get()

    @property
    def mode(self) -> str:
        """Get the current flight mode name (e.g. 'GUIDED', 'HOLD', 'AUTO')."""
        return self._ts_state.mode.get()

    @property
    def velocity(self) -> util.VectorNED:
        """Velocity vector in NED coordinates (m/s)."""
        return util.VectorNED(*self._ts_state.velocity_ned.get())

    @property
    def autopilot_info(self) -> _VersionCompat:
        """Autopilot version information reported by MAVLink."""
        return self._autopilot_info

    @property
    def attitude(self) -> _AttitudeCompat:
        """
        Attitude of the vehicle, all values in radians.
        - pitch/roll are horizon-relative
        - yaw is world relative (north=0)
        """
        return self._ts_state.attitude_val.get()

    def debug_dump(self) -> str:
        """
        Generate a CSV-formatted string of current vehicle state.

        Returns:
            str: Comma-separated values of all tracked vehicle properties.
        """
        nav_controller_output = (
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        if self._last_nav_controller_output is not None:
            nav_controller_output = self._last_nav_controller_output

        mission_item_output = (None, None, None, None)
        if self._last_mission_item_int is not None:
            mission_item_output = self._last_mission_item_int

        props = [
            time.time_ns(),
            self.armed,
            self.attitude,
            self.autopilot_info,
            self.battery,
            self.gps,
            self.heading,
            self.home_coords,
            self.position,
            self.velocity,
            self._ts_state.mode.get(),
            nav_controller_output,
            mission_item_output,
        ]

        return ",".join(map(str, props))

    # Internal logic
    def _internal_update_loop(self) -> None:
        """
        Background loop for periodic internal state maintenance and logging.
        """
        while self._lifecycle.is_running():
            self._internal_update()
            time.sleep(INTERNAL_UPDATE_DELAY_S)

    def _internal_update(self) -> None:
        """
        Perform a single iteration of internal updates.

        Handles verbose logging. Connection loss is detected exclusively via
        the MAVSDK connection_state() subscription in _connection_state_update,
        which fires reliably when the heartbeat is actually lost.
        """
        if self._verbose_logging and (self._verbose_logging_last_log_time + self._verbose_logging_delay < time.time()):
            with self._verbose_log_lock:
                if self._verbose_logging_file_path is None:
                    self._verbose_logging_file_path = Path(
                        f"{self._verbose_logging_file_prefix}_{time.time_ns()}.csv",
                    )
                write_header = not self._verbose_logging_file_path.exists()
                with self._verbose_logging_file_path.open("a", encoding="utf-8") as f:
                    if write_header:
                        # Write header row (F4)
                        f.write(
                            "timestamp_ns,armed,attitude,autopilot_info,battery,gps,heading,home_coords,position,velocity,mode,nav_output,mission_item\n",
                        )
                    log_output = self.debug_dump()
                    f.write(f"{log_output}\n")
                self._verbose_logging_last_log_time = time.time()

        if self._event_log is not None:
            now = time.time()
            if self._structured_telemetry_last_log_time == 0.0 or (self._structured_telemetry_last_log_time + STRUCTURED_TELEMETRY_INTERVAL_S <= now):
                self._structured_telemetry_last_log_time = now
                att = self.attitude
                pos = self.position
                vel = self.velocity
                bat = self.battery
                gps = self.gps
                self._event_log.log_event(
                    "telemetry",
                    lat=pos.lat,
                    lon=pos.lon,
                    alt_m=pos.alt,
                    vel_n_m_s=vel.north,
                    vel_e_m_s=vel.east,
                    vel_d_m_s=vel.down,
                    roll_rad=att.roll,
                    pitch_rad=att.pitch,
                    yaw_rad=att.yaw,
                    heading_deg=self.heading,
                    mode=self.mode,
                    armed=self.armed,
                    battery_pct=bat.level,
                    battery_v=bat.voltage,
                    gps_fix=gps.fix_type,
                    gps_sats=gps.satellites_visible,
                )

    # Special things
    def done_moving(self) -> bool:
        """
        See if the vehicle is ready to move (i.e. if the last movement command
        has been completed). Also makes sure that the vehicle is connected and
        that we haven't aborted.
        """
        if not self.connected or self._aborted:
            return False

        if hasattr(self._ready_to_move, "__func__"):
            return self._ready_to_move.__func__(self)
        return self._ready_to_move(self)

    async def await_ready_to_move(self) -> None:
        """
        Block and wait until the vehicle is ready for the next command.

        Ensures the vehicle is armed and the previous movement has finished.
        """
        if not self.armed:
            await self._arm_vehicle()

        if hasattr(self, "_set_guided_mode"):
            await self._set_guided_mode()
            await asyncio.sleep(ARMING_SEQUENCE_DELAY_S)

        await wait_for_condition(
            self.done_moving,
            timeout=DEFAULT_GOTO_TIMEOUT_S,
            poll_interval=POLLING_DELAY_S,
            timeout_message=(f"Vehicle did not report done_moving within {DEFAULT_GOTO_TIMEOUT_S}s"),
        )

    def _abort(self) -> None:
        """
        Trigger an abort of the current operation if it is marked as abortable.
        """
        if self._abortable:
            # log_to_oeo is blocking, run in thread (E6)
            threading.Thread(
                target=AERPAW_Platform.log_to_oeo,
                args=("[aerpawlib] Aborted.",),
                daemon=True,
            ).start()
            self._abortable = False
            self._aborted = True

    # Verbs
    def close(self) -> None:
        """
        Clean up the `Vehicle` object/any state
        """
        if self._lifecycle.closed:
            return
        logger.debug("Closing vehicle connection...")
        self._lifecycle.mark_closed()

        # Cancel pending MAVSDK operations
        with self._pending_mavsdk_lock:
            pending = list(self._pending_mavsdk_futures)
        for future in pending:
            try:
                future.cancel()
            except Exception as e:
                logger.debug("Error cancelling MAVSDK future: %s", e)

        # Cancel telemetry and command tasks on their own event loop (thread-safe)
        if self._mavsdk_loop is not None and self._mavsdk_loop.is_running():
            for task in self._telemetry_tasks + self._command_tasks:
                with contextlib.suppress(RuntimeError):
                    self._mavsdk_loop.call_soon_threadsafe(task.cancel)

        # Stop MAVSDK loop (only if it's still running)
        if self._mavsdk_loop is not None and self._mavsdk_loop.is_running():
            with contextlib.suppress(RuntimeError):
                self._mavsdk_loop.call_soon_threadsafe(self._mavsdk_loop.stop)

        # Close verbose log writer under the same lock the update loop uses
        with self._verbose_log_lock:
            self._verbose_logging_file_path = None

        if hasattr(self, "_mavsdk_thread") and self._mavsdk_thread.is_alive():
            self._mavsdk_thread.join(timeout=MAVSDK_THREAD_SHUTDOWN_TIMEOUT_S)
            if self._mavsdk_thread.is_alive():
                logger.warning(
                    "MAVSDK thread did not exit within %ds; process will exit",
                    MAVSDK_THREAD_SHUTDOWN_TIMEOUT_S,
                )

        # Clear system reference to help garbage collection release the gRPC server
        self._system = None
        self._mavsdk_loop = None

        logger.info("Vehicle connection closed")

    async def set_armed(self, value: bool) -> None:
        """
        Arm or disarm this vehicle, and wait for it to be armed (if possible).

        Args:
            value: True to arm, False to disarm

        Raises:
            NotArmableError: If attempting to arm when vehicle is not ready
            ArmError: If arming fails
            DisarmError: If disarming fails
        """
        logger.debug(f"set_armed({value}) called")
        if not self._ts_state.is_armable_state.get() and value:
            health_summary = self._get_health_status_summary()
            logger.error(
                f"Cannot arm: vehicle not in armable state. Status: {health_summary}",
            )
            raise NotArmableError(f"Vehicle not armable. Status: {health_summary}")

        try:
            if value:
                logger.debug("Sending arm command...")
                await self._run_on_mavsdk_loop(self._system.action.arm())
            else:
                logger.debug("Sending disarm command...")
                await self._run_on_mavsdk_loop(self._system.action.disarm())

            # Wait for arm state to match
            await wait_for_condition(
                lambda: self._ts_state.armed_state.get() == value,
                timeout=ARMABLE_TIMEOUT_S,
                poll_interval=POLLING_DELAY_S,
                timeout_message=(f"Arm/disarm did not complete within {ARMABLE_TIMEOUT_S}s"),
            )
            logger.debug(f"Vehicle {'armed' if value else 'disarmed'} successfully")
        except ActionError as e:
            logger.error(f"Arm/disarm failed: {e}")
            if value:
                raise ArmError(str(e), original_error=e) from e
            raise DisarmError(str(e), original_error=e) from e

    def _preflight_wait(self, should_arm: bool) -> None:
        """
        Wait for pre-arm conditions (GPS fix, etc.) to be satisfied.

        Args:
            should_arm: Whether to perform arming later.
        """
        logger.debug(f"_preflight_wait(should_arm={should_arm}) called")
        start = time.time()
        last_log = 0.0
        while not self._ts_state.is_armable_state.get():
            if time.time() - start > ARMABLE_TIMEOUT_S:
                logger.warning(
                    f"Timeout waiting for armable state ({ARMABLE_TIMEOUT_S}s). Final status: {self._get_health_status_summary()}",
                )
                break
            # Log status at configured interval
            if time.time() - last_log > ARMABLE_STATUS_LOG_INTERVAL_S:
                logger.debug(
                    f"Waiting for armable state... Status: {self._get_health_status_summary()}",
                )
                last_log = time.time()
            time.sleep(POLLING_DELAY_S)

        if self._ts_state.is_armable_state.get():
            logger.debug("Vehicle is armable")
        else:
            logger.warning(
                f"Vehicle may not be fully ready to arm. Status: {self._get_health_status_summary()}",
            )

        self._will_arm = should_arm

    def initialize(self, should_arm: bool = True) -> None:
        """Wait for pre-arm conditions before mission start (public CLI entry point)."""
        self._preflight_wait(should_arm)

    async def _arm_vehicle(self) -> None:
        """
        Generic pre-mission manipulation of the vehicle into a state that is
        acceptable. MUST be called before anything else.

        In AERPAW environment: waits for safety pilot to arm
        In standalone/SITL: auto-arms the vehicle
        """
        if not self._will_arm:
            logger.debug("Skipping postarm init (disabled)")
            self._init_phase = InitPhase.COMPLETE
            return

        # Re-entrance guard: if another coroutine is already initializing, wait
        if self._init_phase == InitPhase.IN_PROGRESS:
            logger.debug("_arm_vehicle: init already in progress, waiting...")
            await wait_for_condition(
                lambda: self._init_phase == InitPhase.COMPLETE,
                poll_interval=POLLING_DELAY_S,
            )
            return

        self._init_phase = InitPhase.IN_PROGRESS
        try:
            logger.debug("_arm_vehicle() called")

            # Check if we're in AERPAW environment
            is_aerpaw = AERPAW_Platform._connected

            if is_aerpaw:
                # log_to_oeo is blocking, run in thread (E6)
                threading.Thread(
                    target=AERPAW_Platform.log_to_oeo,
                    args=("[aerpawlib] Guided command attempted. Waiting for safety pilot to arm",),
                    daemon=True,
                ).start()
                logger.info("Waiting for safety pilot to arm vehicle...")
                from aerpawlib.cli.progress_bar import update_progress

                update_progress(state="Waiting for safety pilot to arm")

                await wait_for_condition(
                    lambda: self._ts_state.is_armable_state.get(),
                    poll_interval=POLLING_DELAY_S,
                )
                await wait_for_condition(
                    lambda: self.armed,
                    poll_interval=POLLING_DELAY_S,
                )
                update_progress(state="")
            else:
                # In standalone/SITL, auto-arm the vehicle
                logger.info("Standalone mode: auto-arming vehicle...")

                from aerpawlib.cli.progress_bar import update_progress

                try:
                    # Wait for armable state with timeout
                    update_progress(state="Waiting for armable...")
                    try:
                        await wait_for_condition(
                            lambda: self._ts_state.is_armable_state.get(),
                            timeout=CONNECTION_TIMEOUT_S,
                            poll_interval=POLLING_DELAY_S,
                            timeout_message=(f"Vehicle not armable after {CONNECTION_TIMEOUT_S}s - check GPS and pre-flight conditions"),
                        )
                    except TimeoutError as e:
                        health_summary = self._get_health_status_summary()
                        msg = f"{e!s}. Status: {health_summary}"
                        logger.error(msg)
                        raise NotArmableError(msg) from e

                    # Wait for GPS 3D fix explicitly. MAVSDK's is_global_position_ok can
                    # report
                    # true before the autopilot has valid position for GUIDED mode (e.g.
                    # when
                    # SITL is still starting up). Without this, takeoff fails with
                    # "Mode change to GUIDED failed: requires position".
                    logger.debug("Waiting for GPS 3D fix (position ready for GUIDED)...")
                    update_progress(state="Waiting for GPS...")
                    try:
                        await wait_for_condition(
                            lambda: self.gps.fix_type >= GPS_3D_FIX_TYPE,
                            timeout=POSITION_READY_TIMEOUT_S,
                            poll_interval=POLLING_DELAY_S,
                            timeout_message=(f"No GPS 3D fix after {POSITION_READY_TIMEOUT_S}s - ensure SITL/hardware is fully started"),
                        )
                    except TimeoutError as e:
                        health_summary = self._get_health_status_summary()
                        msg = f"{e!s}. Status: {health_summary}"
                        logger.error(msg)
                        raise NotArmableError(msg) from e
                    logger.debug("Waiting for EKF ready...")
                    update_progress(state="Waiting for EKF...")
                    while not self._ts_state.ekf_ready.get():
                        await asyncio.sleep(0.1)
                    logger.debug("Vehicle is armable, sending arm command...")

                    # Arm the vehicle
                    await self.set_armed(True)
                    logger.info("Vehicle armed successfully")
                finally:
                    update_progress(state="")

            await asyncio.sleep(ARMING_SEQUENCE_DELAY_S)

            self._abortable = True

            # Wait for home position to be populated from telemetry (up to 5s)
            logger.debug("Waiting for auto-set home position...")
            await wait_for_condition(
                lambda: self._ts_state.home_position.get() is not None,
                timeout=_HOME_WAIT_TIMEOUT_S,
                poll_interval=POLLING_DELAY_S,
                timeout_message=(f"Home position not available within {_HOME_WAIT_TIMEOUT_S}s"),
            )

            self._ts_state.captured_home.set(self.home_coords)
            logger.debug(f"Home location set to: {self.home_coords}")
            self._init_phase = InitPhase.COMPLETE
        finally:
            if self._init_phase == InitPhase.IN_PROGRESS:
                self._init_phase = InitPhase.PENDING

    async def goto_coordinates(
        self,
        coordinates: util.Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
    ) -> None:
        """
        Make the vehicle go to provided coordinates.

        Args:
            coordinates: Target position
            tolerance: Distance in meters to consider destination reached
            target_heading: Optional heading to maintain during movement

        Raises:
            NotImplementedForVehicleError: Generic vehicles cannot navigate
        """
        raise NotImplementedForVehicleError("goto_coordinates", "generic Vehicle")

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """
        [NOT SUPPORTED] This API function is not supported because velocity control is currently blocked by the filter. This may (and will) change in the future.

        Set a drone's velocity that it will use for `duration` seconds.

        Args:
            velocity_vector: Velocity in NED frame
            global_relative: If True, vector is in global frame; if False, in body frame
            duration: How long to maintain velocity (None = until changed)

        Raises:
            NotImplementedForVehicleError: Generic vehicles cannot set velocity
        """
        raise NotImplementedForVehicleError("set_velocity", "generic Vehicle")

    async def set_groundspeed(self, velocity: float) -> None:
        """
        Set a vehicle's cruise velocity as used by the autopilot.

        Args:
            velocity: Groundspeed in m/s

        Raises:
            ValueError: If velocity is out of acceptable range
        """
        # Note: speed bounds (min_speed / max_speed) are enforced by the
        # SafetyCheckerServer via validate_change_speed_command. No redundant
        # constant-based check here.
        logger.debug(f"set_groundspeed({velocity}) called")
        try:
            await self._run_on_mavsdk_loop(
                self._system.action.set_current_speed(velocity),
            )
            logger.debug(f"Current speed set to {velocity} m/s")
        except ActionError:
            logger.debug("set_current_speed not supported by autopilot")
            pass  # Not all autopilots support this

    async def _stop(self) -> None:
        """
        Stop any background movement tasks.
        """
        self._ready_to_move = lambda _: True

    def _get_health_status_summary(self) -> str:
        """
        Get a human-readable summary of the current vehicle health status.
        """
        health = self._ts_state.health_val.get()
        if health is None:
            return "UNKNOWN (no telemetry)"

        return (
            f"Global: {'OK' if health.is_global_position_ok else 'FAIL'}, "
            f"Home: {'OK' if health.is_home_position_ok else 'FAIL'}, "
            f"Local: {'OK' if health.is_local_position_ok else 'FAIL'}, "
            f"Pre-arm: {'OK' if self._ts_state.prearm_checks_ok.get() else 'FAIL'}, "
            f"EKF: {'OK' if self._ts_state.ekf_ready.get() else 'FAIL'}, "
            f"Armable: {'OK' if health.is_armable else 'FAIL'}, "
            f"Gyro: {'OK' if health.is_gyrometer_calibration_ok else 'FAIL'}, "
            f"Accel: {'OK' if health.is_accelerometer_calibration_ok else 'FAIL'}, "
            f"Mag: {'OK' if health.is_magnetometer_calibration_ok else 'FAIL'}, "
            f"Fix: {self.gps.fix_type} ({self.gps.satellites_visible} sats)"
        )
