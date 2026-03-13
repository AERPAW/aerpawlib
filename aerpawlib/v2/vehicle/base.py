"""
Base vehicle for aerpawlib v2.

Single async loop, direct MAVSDK calls, native telemetry.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, List, Optional, TYPE_CHECKING, Tuple
import json

import math

if TYPE_CHECKING:
    pass

from mavsdk import System
from mavsdk.action import ActionError

from ..constants import (
    CONNECTION_TIMEOUT_S,
    MIN_POSITION_TOLERANCE_M,
    MAX_POSITION_TOLERANCE_M,
    MAV_SYS_STATUS_PREARM_CHECK
)
from ..exceptions import (
    AerpawConnectionError,
    ConnectionTimeoutError,
    NotArmableError,
)
from ..log import LogComponent, get_logger
from ..types import Attitude, Battery, Coordinate, GPSInfo, VectorNED
from .state import VehicleState

logger = get_logger(LogComponent.VEHICLE)

_MAVSDK_VALID_SCHEMES = frozenset(
    ("udpin", "tcpin",  "serial", "tcp", "udp")
)


def _validate_connection_string(conn_str: str) -> None:
    """Raise AerpawConnectionError immediately if conn_str is malformed.

    Prevents spawning mavsdk_server with an invalid URL, which would otherwise
    cause a silent timeout hang instead of a fast, clear error.
    """
    s = conn_str.strip()
    if "://" not in s:
        raise AerpawConnectionError(
            f"Invalid connection string {conn_str!r}: missing '://'. "
            "Expected format e.g. 'udpin://0.0.0.0:14550', "
            "'udpout://host:port', 'tcpin://host:port', "
            "'tcpout://host:port', or 'serial:///dev/path[:baud]'."
        )
    scheme = s.split("://")[0].lower()
    if scheme not in _MAVSDK_VALID_SCHEMES:
        raise AerpawConnectionError(
            f"Invalid connection string {conn_str!r}: unknown scheme {scheme!r}. "
            f"Supported schemes: {', '.join(sorted(_MAVSDK_VALID_SCHEMES))}."
        )


def _validate_tolerance(tolerance: float, param_name: str = "tolerance") -> float:
    """Validate that tolerance is within acceptable bounds.

    Args:
        tolerance: Tolerance value in metres to validate.
        param_name: Name of the parameter (used in error messages).

    Returns:
        The validated tolerance value (unchanged).

    Raises:
        ValueError: If tolerance is outside [MIN_POSITION_TOLERANCE_M,
            MAX_POSITION_TOLERANCE_M].
    """
    if not (MIN_POSITION_TOLERANCE_M <= tolerance <= MAX_POSITION_TOLERANCE_M):
        raise ValueError(
            f"{param_name} must be between {MIN_POSITION_TOLERANCE_M} and "
            f"{MAX_POSITION_TOLERANCE_M}, got {tolerance}"
        )
    return tolerance


async def _wait_for_condition(
    condition: Callable[[], bool],
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    timeout_message: str = "Operation timed out",
) -> bool:
    """Wait until a condition callable returns True.

    Args:
        condition: Zero-argument callable; returns True when the wait is over.
        timeout: Maximum seconds to wait. None means wait indefinitely.
        poll_interval: Seconds between condition checks; also yields the
            event loop between checks.
        timeout_message: Message used in the TimeoutError if the wait expires.

    Returns:
        True when the condition becomes True.

    Raises:
        TimeoutError: If timeout is reached before the condition is satisfied.
    """
    start = time.monotonic()
    while not condition():
        if timeout is not None and (time.monotonic() - start) > timeout:
            logger.warning(f"_wait_for_condition timeout after {timeout}s: {timeout_message}")
            raise TimeoutError(timeout_message)
        await asyncio.sleep(poll_interval)  # Justified: yield to loop, allow telemetry
    return True


class VehicleTask:
    """
    Handle for non-blocking commands with progress and cancellation.

    Use event-driven completion via position/landed_state subscriptions.
    """

    def __init__(self) -> None:
        self._done = asyncio.Event()
        self._cancelled = False
        self._progress: float = 0.0
        self._error: Optional[Exception] = None
        self._on_cancel: Optional[Callable[[], object]] = None
        self._cancel_tasks: List[asyncio.Task] = []

    @property
    def progress(self) -> float:
        """Progress 0.0 to 1.0."""
        return self._progress

    def is_done(self) -> bool:
        """True if the command has completed (success, error, or cancelled)."""
        return self._done.is_set()

    def set_progress(self, value: float) -> None:
        """Update progress (0.0-1.0). Internal use by command implementation."""
        self._progress = max(0.0, min(1.0, value))

    def set_complete(self) -> None:
        """Mark command as successfully complete. Internal use."""
        self._error = None
        self._done.set()

    def set_error(self, error: Exception) -> None:
        """Mark command as failed with error. Internal use."""
        self._error = error
        self._done.set()

    def set_on_cancel(self, callback: Callable[[], object]) -> None:
        """Set async callback to run when cancel() is called (e.g. RTL to stop goto)."""
        self._on_cancel = callback

    def cancel(self) -> None:
        """Request cancellation. Invokes on_cancel callback if set to stop the vehicle."""
        logger.debug("VehicleTask: cancel requested")
        self._cancelled = True
        if self._on_cancel:
            try:
                loop = asyncio.get_running_loop()
                result = self._on_cancel()
                if asyncio.iscoroutine(result):
                    t = loop.create_task(result)
                    self._cancel_tasks.append(t)
            except RuntimeError:
                logger.warning(
                    "VehicleTask.cancel() called outside an async context; "
                    "on_cancel callback will not run. The vehicle may continue its current task."
                )

    def is_cancelled(self) -> bool:
        """Return True if cancel() has been called."""
        return self._cancelled

    async def wait_done(self) -> None:
        """Wait until command completes or is cancelled."""
        await self._done.wait()
        if self._error is not None:
            raise self._error


class Vehicle:
    """
    Base vehicle with async connect, single-loop telemetry, no ThreadSafeValue.
    """

    def __init__(
        self,
        system: System,
        connection_string: str,
        mavsdk_server_port: int = 50051,
        *,
        safety: Optional[Any] = None,
    ) -> None:
        """
        Args:
            system: MAVSDK System instance.
            connection_string: MAVLink connection string.
            mavsdk_server_port: gRPC port for mavsdk_server.
            safety: SafetyCheckerClient or NoOpSafetyChecker for validation.
                    None disables safety checks in can_takeoff/can_goto/can_land.
        """
        self._system = system
        self._connection_string = connection_string
        self._mavsdk_server_port = mavsdk_server_port
        self._state = VehicleState()
        self._telemetry_tasks: List[asyncio.Task] = []
        self._command_tasks: List[asyncio.Task] = []
        self._running = True
        self._closed = False
        self._ready_to_move: Callable[["Vehicle"], bool] = lambda _: True
        self._heartbeat_tick_cb: Optional[Callable[[], None]] = None
        self._mission_start_time: Optional[float] = None
        self._will_arm: bool = True
        self._expecting_disarm: bool = False
        self._unexpected_disarm_event: asyncio.Event = asyncio.Event()
        self.safety: Optional[Any] = safety

    def set_heartbeat_tick_callback(self, cb: Callable[[], None]) -> None:
        """Set a callback invoked whenever telemetry is received.

        Args:
            cb: Zero-argument callable; typically ConnectionHandler.heartbeat_tick.
        """
        self._heartbeat_tick_cb = cb

    def _heartbeat_tick(self) -> None:
        """Called from telemetry when we receive data (heartbeat indicator)."""
        if self._heartbeat_tick_cb:
            self._heartbeat_tick_cb()

    def heartbeat_tick(self) -> None:
        """Protocol method for ConnectionHandler."""
        self._heartbeat_tick()

    @property
    def connected(self) -> bool:
        """Return True if the vehicle is running and not closed."""
        return self._running and not self._closed

    @property
    def closed(self) -> bool:
        """True if the vehicle connection has been closed."""
        return self._closed

    @property
    def position(self) -> Coordinate:
        return self._state.position

    @property
    def home_coords(self) -> Optional[Coordinate]:
        return self._state.home_coords

    @property
    def home_amsl(self) -> float:
        return self._state.home_amsl

    @property
    def battery(self) -> Battery:
        return self._state.battery

    @property
    def gps(self) -> GPSInfo:
        return self._state.gps

    @property
    def armed(self) -> bool:
        return self._state.armed

    @property
    def heading(self) -> float:
        return self._state.heading

    @property
    def velocity(self) -> VectorNED:
        return self._state.velocity

    @property
    def attitude(self) -> Attitude:
        return self._state.attitude

    @property
    def mode(self) -> str:
        return self._state.mode

    @property
    def armable(self) -> bool:
        return self._state.armable

    async def can_takeoff(
        self, altitude: float, min_battery_percent: float = 10.0
    ) -> Tuple[bool, str]:
        """
        Check if takeoff would succeed. Local checks plus optional SafetyCheckerClient.

        Returns:
            (ok, message) - ok is True if command would succeed.
        """
        logger.debug(f"can_takeoff: checking altitude={altitude}m battery>={min_battery_percent}%")
        if not self._state.armable:
            logger.debug(f"can_takeoff: rejected (not armable) {self._get_health_summary()}")
            return False, f"Vehicle not armable: {self._get_health_summary()}"
        if self.gps.fix_type < 3:
            logger.debug(f"can_takeoff: rejected (no 3D GPS fix_type={self.gps.fix_type})")
            return False, f"No 3D GPS fix (fix_type={self.gps.fix_type})"
        if self.battery.level < min_battery_percent:
            logger.debug(f"can_takeoff: rejected (battery {self.battery.level}% < {min_battery_percent}%)")
            return False, f"Battery {self.battery.level}% below {min_battery_percent}%"
        if self.safety is not None:
            ok, msg = await self.safety.validate_takeoff(
                altitude, self.position.lat, self.position.lon
            )
            logger.debug(f"can_takeoff: safety check ok={ok} msg={msg!r}")
            if not ok:
                return False, msg
        logger.debug("can_takeoff: passed")
        return True, ""

    async def can_goto(
        self,
        target: Coordinate,
        tolerance: float = 2.0,
    ) -> Tuple[bool, str]:
        """
        Check if goto would succeed. Local checks plus optional SafetyCheckerClient.

        Returns:
            (ok, message) - ok is True if command would succeed.
        """
        logger.debug(f"can_goto: checking target=({target.lat:.6f},{target.lon:.6f}) tol={tolerance}m")
        if not (MIN_POSITION_TOLERANCE_M <= tolerance <= MAX_POSITION_TOLERANCE_M):
            return False, (
                f"Tolerance must be between {MIN_POSITION_TOLERANCE_M} and "
                f"{MAX_POSITION_TOLERANCE_M}m"
            )
        if self.safety is not None:
            ok, msg = await self.safety.validate_waypoint(self.position, target)
            logger.debug(f"can_goto: safety check ok={ok} msg={msg!r}")
            if not ok:
                return False, msg
        logger.debug("can_goto: passed")
        return True, ""

    async def can_land(self) -> Tuple[bool, str]:
        """
        Check if land would succeed. Optional SafetyCheckerClient only.

        Returns:
            (ok, message) - ok is True if command would succeed.
        """
        logger.debug(f"can_land: checking pos=({self.position.lat:.6f},{self.position.lon:.6f})")
        if self.safety is not None:
            ok, msg = await self.safety.validate_landing(
                self.position.lat, self.position.lon
            )
            logger.debug(f"can_land: safety check ok={ok} msg={msg!r}")
            if not ok:
                return False, msg
        logger.debug("can_land: passed")
        return True, ""

    @classmethod
    async def connect(
        cls,
        connection_string: str,
        mavsdk_server_port: int = 50051,
        *,
        timeout: float = CONNECTION_TIMEOUT_S,
        safety: Optional[Any] = None,
    ) -> "Vehicle":
        """Connect to vehicle and start telemetry.

        Args:
            connection_string: MAVLink connection string (e.g. ``udp://:14550``).
            mavsdk_server_port: gRPC port for the mavsdk_server process.
            timeout: Connection timeout in seconds.
            safety: SafetyCheckerClient or NoOpSafetyChecker. None disables
                safety checks in can_takeoff/can_goto/can_land.

        Returns:
            Initialised and connected Vehicle instance with telemetry running.

        Raises:
            ConnectionTimeoutError: If no heartbeat is received within timeout.
        """
        logger.info(
            f"Connecting to vehicle at {connection_string} "
            f"(port={mavsdk_server_port}, timeout={timeout}s)"
        )
        _validate_connection_string(connection_string)
        system = System(port=mavsdk_server_port)
        await asyncio.wait_for(
            system.connect(system_address=connection_string),
            timeout=timeout,
        )
        logger.debug("MAVSDK connect() returned, waiting for connection state")

        # Wrap in wait_for so an invalid connection string doesn't hang forever
        # (the async generator may never yield if MAVSDK gets no heartbeat).
        async def _wait_for_heartbeat() -> None:
            async for state in system.core.connection_state():
                if state.is_connected:
                    return

        try:
            await asyncio.wait_for(_wait_for_heartbeat(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout: no heartbeat within {timeout}s")
            raise ConnectionTimeoutError(
                timeout,
                "Connection established but no heartbeat within timeout",
            )

        # Create instance and start telemetry
        self = cls(system, connection_string, mavsdk_server_port, safety=safety)
        await self._start_telemetry()
        logger.info("Vehicle connected and telemetry started")
        return self

    async def _start_telemetry(self) -> None:
        """Start telemetry subscriptions on same loop."""
        logger.debug("Starting telemetry subscriptions (position, attitude, velocity, gps, battery, mode, armed, health, home)")

        # Throttle interval for periodic telemetry debug logs (seconds)
        _telem_log_interval = 5.0

        def _telem_log_throttle(last: list, interval: float = _telem_log_interval) -> bool:
            """Return True if we should log (throttled). Mutates last[0]."""
            now = time.monotonic()
            if last[0] == 0 or (now - last[0]) >= interval:
                last[0] = now
                return True
            return False

        async def _position_update() -> None:
            first = [True]
            last_log = [0.0]
            async for position in self._system.telemetry.position():
                if not self._running:
                    return
                self._state.update_position(
                    position.latitude_deg,
                    position.longitude_deg,
                    position.relative_altitude_m,
                    position.absolute_altitude_m,
                )
                self._heartbeat_tick()
                if first[0]:
                    logger.info(
                        f"Telemetry: position stream active (lat={position.latitude_deg:.6f}, lon={position.longitude_deg:.6f}, alt={position.relative_altitude_m:.1f}m)"
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: position lat={position.latitude_deg:.6f} lon={position.longitude_deg:.6f} alt={position.relative_altitude_m:.1f}m"
                    )

        async def _attitude_update() -> None:
            first = [True]
            last_log = [0.0]
            async for att in self._system.telemetry.attitude_euler():
                if not self._running:
                    return
                self._state.update_attitude(
                    math.radians(att.roll_deg),
                    math.radians(att.pitch_deg),
                    math.radians(att.yaw_deg),
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: attitude stream active (roll={att.roll_deg:.1f} pitch={att.pitch_deg:.1f} yaw={att.yaw_deg:.1f} deg)"
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: attitude roll={att.roll_deg:.1f} pitch={att.pitch_deg:.1f} yaw={att.yaw_deg:.1f} deg"
                    )

        async def _velocity_update() -> None:
            first = [True]
            last_log = [0.0]
            async for vel in self._system.telemetry.velocity_ned():
                if not self._running:
                    return
                self._state.update_velocity(
                    vel.north_m_s, vel.east_m_s, vel.down_m_s
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: velocity stream active (N={vel.north_m_s:.2f} E={vel.east_m_s:.2f} D={vel.down_m_s:.2f} m/s)"
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: velocity N={vel.north_m_s:.2f} E={vel.east_m_s:.2f} D={vel.down_m_s:.2f} m/s"
                    )

        async def _gps_update() -> None:
            first = [True]
            last_log = [0.0]
            async for gps in self._system.telemetry.gps_info():
                if not self._running:
                    return
                fix = gps.fix_type.value if hasattr(gps.fix_type, "value") else gps.fix_type
                self._state.update_gps(fix, gps.num_satellites)
                if first[0]:
                    logger.info(
                        f"Telemetry: gps stream active (fix_type={fix}, sats={gps.num_satellites})"
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: gps fix_type={fix} sats={gps.num_satellites}"
                    )

        async def _battery_update() -> None:
            first = [True]
            last_log = [0.0]
            async for bat in self._system.telemetry.battery():
                if not self._running:
                    return
                current = getattr(bat, "current_battery_a", 0.0) or 0.0
                self._state.update_battery(
                    bat.voltage_v, current, int(bat.remaining_percent)
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: battery stream active ({bat.voltage_v:.1f}V, {int(bat.remaining_percent)}%)"
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: battery {bat.voltage_v:.1f}V {current:.1f}A {int(bat.remaining_percent)}%"
                    )

        async def _flight_mode_update() -> None:
            first = [True]
            prev_mode: list = [None]
            async for mode in self._system.telemetry.flight_mode():
                if not self._running:
                    return
                mode_name = mode.name
                self._state.update_mode(mode_name)
                if first[0]:
                    logger.info(f"Telemetry: flight_mode stream active (mode={mode_name})")
                    first[0] = False
                    prev_mode[0] = mode_name
                elif prev_mode[0] != mode_name:
                    logger.info(f"Telemetry: flight_mode changed {prev_mode[0]} -> {mode_name}")
                    prev_mode[0] = mode_name

        async def _armed_update() -> None:
            first = [True]
            prev_armed: list = [None]
            async for armed in self._system.telemetry.armed():
                if not self._running:
                    return
                self._state.update_armed(armed)
                if first[0]:
                    logger.info(f"Telemetry: armed stream active (armed={armed})")
                    first[0] = False
                    prev_armed[0] = armed
                elif prev_armed[0] != armed:
                    logger.info(f"Telemetry: armed changed {prev_armed[0]} -> {armed}")
                    if prev_armed[0] is True and not armed and not self._expecting_disarm:
                        logger.warning(
                            "Vehicle disarmed unexpectedly! "
                            "Signalling experiment termination."
                        )
                        self._unexpected_disarm_event.set()
                    prev_armed[0] = armed

        async def _health_update() -> None:
            first = [True]
            async for health in self._system.telemetry.health():
                if not self._running:
                    return
                self._state.update_armable(
                    health.is_global_position_ok,
                    health.is_local_position_ok,
                    health.is_home_position_ok,
                    health.is_armable,
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: health stream active (armable={health.is_armable})"
                    )
                    first[0] = False

        async def _home_update() -> None:
            first = [True]
            async for home in self._system.telemetry.home():
                if not self._running:
                    return
                self._state.update_home(
                    home.latitude_deg,
                    home.longitude_deg,
                    home.relative_altitude_m,
                    home.absolute_altitude_m,
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: home stream active (lat={home.latitude_deg:.6f} lon={home.longitude_deg:.6f} alt={home.relative_altitude_m:.1f}m)"
                    )
                    first[0] = False

        async def _mavlink_status_update() -> None:
            async for msg in self._system.mavlink_direct.message("SYS_STATUS"):
                if not self._running:
                    return
                try:
                    fields = json.loads(msg.fields_json)
                    health = fields.get("onboard_control_sensors_health", 0)
                    self._state.update_prearm_bits((health & MAV_SYS_STATUS_PREARM_CHECK) == MAV_SYS_STATUS_PREARM_CHECK)
                except Exception as e:
                    logger.debug(f"Error parsing SYS_STATUS: {e}")

        for coro in [
            _position_update,
            _attitude_update,
            _velocity_update,
            _gps_update,
            _battery_update,
            _flight_mode_update,
            _armed_update,
            _health_update,
            _home_update,
            _mavlink_status_update,
        ]:
            task = asyncio.create_task(coro())
            self._telemetry_tasks.append(task)
        logger.debug(f"Started {len(self._telemetry_tasks)} telemetry tasks")

    def done_moving(self) -> bool:
        """Return True if the vehicle is ready to accept the next command."""
        return self._ready_to_move(self)

    async def _arm_vehicle(self) -> None:
        """Arm and prepare for mission. Override in Drone/Rover."""
        raise NotImplementedError("Override in subclass")

    async def await_ready_to_move(self) -> None:
        """Wait until vehicle is ready for next command."""
        if self._closed:
            raise RuntimeError("Cannot await_ready_to_move: vehicle is closed")
        if self._will_arm and not self.armed:
            logger.debug("await_ready_to_move: vehicle not armed, running arm sequence")
            await self._arm_vehicle()
        logger.debug("await_ready_to_move: waiting for done_moving")
        start = time.monotonic()
        last_log = 0.0
        while not self.done_moving():
            if self._closed:
                raise RuntimeError("Vehicle closed while waiting for ready_to_move")
            elapsed = time.monotonic() - start
            if elapsed > 300.0:
                raise TimeoutError("Vehicle did not report ready within timeout")
            now = time.monotonic()
            if now - last_log >= 10.0:
                logger.debug(
                    "await_ready_to_move: still waiting (elapsed=%.0fs mode=%s armed=%s)",
                    elapsed, self.mode, self.armed,
                )
                last_log = now
            await asyncio.sleep(0.05)
        logger.debug("await_ready_to_move: vehicle ready")

    async def set_armed(self, value: bool) -> None:
        """
        Arm or disarm the vehicle.

        Args:
            value: True to arm, False to disarm.

        Raises:
            RuntimeError: If the vehicle is closed.
            NotArmableError: If the vehicle reports it cannot be armed.
            ArmError: If the arm command fails.
            DisarmError: If the disarm command fails.
        """
        if self._closed or self._system is None:
            raise RuntimeError("Cannot set_armed: vehicle is closed")
        logger.info(f"set_armed({value})")
        if value and not self._state.armable:
            logger.warning(f"Arm rejected: {self._get_health_summary()}")
            raise NotArmableError(
                f"Vehicle not armable: {self._get_health_summary()}"
            )
        if not value:
            self._expecting_disarm = True
        try:
            if value:
                await self._system.action.arm()
            else:
                await self._system.action.disarm()
            await _wait_for_condition(
                lambda: self._state.armed == value,
                timeout=60.0,
                poll_interval=0.05,
                timeout_message="Arm/disarm did not complete within 60s",
            )
        except ActionError as e:
            from ..exceptions import ArmError, DisarmError

            if value:
                raise ArmError(str(e), original_error=e)
            raise DisarmError(str(e), original_error=e)
        finally:
            if not value:
                self._expecting_disarm = False
        logger.debug(f"set_armed({value}) completed successfully")

    def _get_health_summary(self) -> str:
        """Return a human-readable summary of current health/GPS/armable status.

        Returns:
            Short string describing GPS fix type, satellites visible, and
            armable flag.
        """
        return (
            f"GPS fix: {self._state.gps.fix_type}, "
            f"sats: {self._state.gps.satellites_visible}, "
            f"armable: {self._state.armable}"
        )

    async def _stop(self) -> None:
        """Stop background movement."""
        self._ready_to_move = lambda _: True

    async def set_groundspeed(self, velocity: float) -> None:
        """Set the maximum ground speed of the vehicle.

        Args:
            velocity: Maximum speed in m/s.
        """
        if self._closed or self._system is None:
            raise RuntimeError("Cannot set_groundspeed: vehicle is closed")
        try:
            await self._system.action.set_maximum_speed(velocity)
        except Exception as e:
            logger.warning("set_groundspeed failed: %s", e)

    def close(self) -> None:
        """Clean up. Cancels all telemetry and command tasks."""
        if self._closed:
            logger.debug("close() called but already closed")
            return
        logger.info("Closing vehicle connection")
        self._closed = True
        self._running = False
        for task in getattr(self, "_telemetry_tasks", []):
            task.cancel()
        for task in getattr(self, "_command_tasks", []):
            task.cancel()
        self._telemetry_tasks.clear()
        if hasattr(self, "_command_tasks"):
            self._command_tasks.clear()
        logger.info("Vehicle connection closed")
        self._system = None

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = 2.0,
        target_heading: Optional[float] = None,
    ) -> None:
        """Navigate to the given coordinates.

        Override in Drone and Rover subclasses.

        Args:
            coordinates: Target position.
            tolerance: Arrival tolerance in metres.
            target_heading: Optional heading to face at the destination.

        Raises:
            NotImplementedError: Always; must be overridden in a subclass.
        """
        raise NotImplementedError("Generic Vehicle cannot navigate")


class DummyVehicle(Vehicle):
    """No-op vehicle for testing without hardware."""

    def __init__(self, *, safety: Optional[Any] = None) -> None:
        """Initialise a no-op vehicle with default state suitable for dry-runs.

        Args:
            safety: Optional safety checker; defaults to None (no safety checks).
        """
        self._state = VehicleState()
        self._state.update_position(35.727436, -78.696587, 0.0, 0.0)
        self._state.update_gps(3, 10)
        self._state.update_battery(12.6, 0.0, 100)
        self._state.update_home(35.727436, -78.696587, 0.0, 0.0)
        self._state.update_armable(True, True, True)
        self._system = None
        self._connection_string = ""
        self._mavsdk_server_port = 50051
        self._telemetry_tasks = []
        self._command_tasks = []
        self._running = True
        self._closed = False
        self._ready_to_move = lambda _: True
        self._heartbeat_tick_cb = None
        self._mission_start_time = None
        self._will_arm = False
        self._expecting_disarm = False
        self._unexpected_disarm_event = asyncio.Event()
        self.safety = safety

    @classmethod
    async def connect(
        cls,
        connection_string: str = "",
        mavsdk_server_port: int = 50051,
        *,
        timeout: float = CONNECTION_TIMEOUT_S,
        safety: Optional[Any] = None,
    ) -> "DummyVehicle":
        """Return a DummyVehicle without opening any real connection.

        Args:
            connection_string: Ignored.
            mavsdk_server_port: Ignored.
            timeout: Ignored.
            safety: Passed to the DummyVehicle constructor.

        Returns:
            A new DummyVehicle instance.
        """
        return cls(safety=safety)

    async def goto_coordinates(
        self,
        coordinates: "Coordinate",
        tolerance: float = 2.0,
        target_heading: Optional[float] = None,
    ) -> None:
        """No-op for dry-run."""
        pass

    def close(self) -> None:
        self._closed = True
        self._running = False
