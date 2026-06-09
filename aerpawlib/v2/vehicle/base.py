"""
Base vehicle for aerpawlib v2.

Single async loop, direct MAVSDK calls, native telemetry.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from mavsdk import System
from mavsdk.action import ActionError

from aerpawlib.v2.constants import (
    ARMABLE_STATUS_LOG_INTERVAL_S,
    ARMABLE_TIMEOUT_S,
    ARMING_SEQUENCE_DELAY_S,
    CONNECTION_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_MAVSDK_SERVER_PORT,
    DEFAULT_POSITION_TOLERANCE_M,
    GPS_3D_FIX_TYPE,
    HOME_POSITION_TIMEOUT_S,
    MAV_SYS_STATUS_PREARM_CHECK,
    MAX_POSITION_TOLERANCE_M,
    MIN_POSITION_TOLERANCE_M,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
    POST_ARM_STABILIZE_DELAY_S,
    READY_MOVE_LOG_INTERVAL_S,
)
from aerpawlib.v2.exceptions import (
    ArmError,
    ConnectionTimeoutError,
    DisarmError,
    NotArmableError,
)
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.safety.validation import PreflightChecks

from .connection_helpers import (
    _validate_connection_string,
    _wait_for_condition,
)
from .connection_state import ConnectionState
from .mock_state import default_mock_state
from .navigation import goto_bearing_distance, goto_cardinal, goto_offset
from .offboard import OffboardSession
from .state import VehicleState
from .task import VehicleTask

if TYPE_CHECKING:
    from aerpawlib.v2.types import (
        Attitude,
        Battery,
        Coordinate,
        GPSInfo,
        VectorNED,
    )

logger = get_logger(LogComponent.VEHICLE)


class Vehicle:
    """
    Base vehicle with async connect, single-loop telemetry, no ThreadSafeValue.

    Internal state map:
    - ``_connection`` (ConnectionState): link_alive, telemetry freshness, closed
    - ``_state`` (VehicleState): telemetry mirrored by public properties
    - ``_ready_to_move``: movement-completion predicate for command gating
    """

    def __init__(
        self,
        system: System,
        connection_string: str,
        mavsdk_server_port: int = DEFAULT_MAVSDK_SERVER_PORT,
        *,
        safety: Any | None = None,
        aerpaw_platform: Any | None = None,
    ) -> None:
        """
        Args:
            system: MAVSDK System instance.
            connection_string: MAVLink connection string.
            mavsdk_server_port: gRPC port for mavsdk_server.
            safety: SafetyCheckerClient or NoOpSafetyChecker for validation.
                    None disables safety checks in can_takeoff/can_goto/can_land.
            aerpaw_platform: AerpawPlatform instance for AERPAW environment integration.
                    None disables AERPAW platform notifications.
        """
        self._system = system
        self._connection_string = connection_string
        self._mavsdk_server_port = mavsdk_server_port
        self._state = VehicleState()
        self._telemetry_tasks: list[asyncio.Task] = []
        self._command_tasks: list[asyncio.Task] = []
        self._connection = ConnectionState()
        self._ready_to_move: Callable[[Vehicle], bool] = lambda _: True
        self._mission_start_time: float | None = None
        self._will_arm: bool = True
        self._expecting_disarm: bool = False
        self._unexpected_disarm_event: asyncio.Event = asyncio.Event()
        self.safety: Any | None = safety
        self._event_log: Any | None = None
        self._aerpaw_platform = aerpaw_platform
        self._offboard = OffboardSession()

    @property
    def link_alive(self) -> bool:
        """Return True when MAVSDK reports an active MAVLink link."""
        return self._connection.link_alive

    def set_event_log(self, event_log: Any | None) -> None:
        """Set the structured event logger for mission events."""
        self._event_log = event_log

    def _log_structured_telemetry_snapshot(self) -> None:
        """Emit a single JSONL telemetry event (throttled by caller)."""
        if not self._event_log:
            return
        s = self._state
        att = s.attitude
        pos = s.position
        vel = s.velocity
        bat = s.battery
        gps = s.gps
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
            heading_deg=s.heading,
            mode=s.mode,
            armed=s.armed,
            battery_pct=bat.level,
            battery_v=bat.voltage,
            gps_fix=gps.fix_type,
            gps_sats=gps.satellites_visible,
        )

    def heartbeat_tick(self) -> None:
        """Record telemetry activity (VehicleProtocol / test mocks)."""
        self._connection.record_telemetry()

    def watch_disconnect(
        self,
        timeout: float,
        *,
        on_disconnect: Callable[[], None] | None = None,
    ) -> asyncio.Future:
        """Return a Future that completes with HeartbeatLostError on disconnect."""
        return self._connection.watch_disconnect(timeout, on_disconnect=on_disconnect)

    @property
    def connected(self) -> bool:
        """Return True if the vehicle has an active connection (receiving heartbeats)."""
        return self._connection.connected

    @property
    def closed(self) -> bool:
        """True if the vehicle connection has been closed."""
        return self._connection.closed

    @property
    def position(self) -> Coordinate:
        """Return the most recent global position estimate."""
        return self._state.position

    @property
    def home_coords(self) -> Coordinate | None:
        """Return the stored home coordinate, if available."""
        return self._state.home_coords

    @property
    def home_amsl(self) -> float:
        """Return home altitude above mean sea level in metres."""
        return self._state.home_amsl

    @property
    def battery(self) -> Battery:
        """Return latest battery telemetry."""
        return self._state.battery

    @property
    def gps(self) -> GPSInfo:
        """Return latest GPS telemetry."""
        return self._state.gps

    @property
    def armed(self) -> bool:
        """Return whether the vehicle is armed."""
        return self._state.armed

    @property
    def heading(self) -> float:
        """Return heading in degrees."""
        return self._state.heading

    @property
    def velocity(self) -> VectorNED:
        """Return current NED velocity vector."""
        return self._state.velocity

    @property
    def attitude(self) -> Attitude:
        """Return latest roll, pitch, and yaw values."""
        return self._state.attitude

    @property
    def mode(self) -> str:
        """Return current autopilot mode name."""
        return self._state.mode

    @property
    def armable(self) -> bool:
        """Return whether pre-arm checks currently pass."""
        return self._state.armable

    @property
    def ekf_ready(self) -> bool:
        """Return True if EKF reports ready for takeoff (ArduPilot)."""
        return self._state.ekf_ready

    async def can_takeoff(
        self,
        altitude: float,
        min_battery_percent: float = 10.0,
    ) -> tuple[bool, str]:
        """
        Check if takeoff would succeed. Local checks plus optional SafetyCheckerClient.

        Returns:
            (ok, message) - ok is True if command would succeed.
        """
        logger.debug(
            f"can_takeoff: checking altitude={altitude}m battery>={min_battery_percent}%",
        )
        if not self._state.armable:
            logger.debug(
                f"can_takeoff: rejected (not armable) {self._get_health_summary()}",
            )
            return False, f"Vehicle not armable: {self._get_health_summary()}"
        if not PreflightChecks.check_gps_fix(self):
            return False, f"No 3D GPS fix (fix_type={self.gps.fix_type})"
        if not PreflightChecks.check_battery(self, min_battery_percent):
            return (
                False,
                f"Battery {self.battery.level}% below {min_battery_percent}%",
            )
        if self.safety is not None:
            ok, msg = await self.safety.validate_takeoff(
                altitude,
                self.position.lat,
                self.position.lon,
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
    ) -> tuple[bool, str]:
        """
        Check if goto would succeed. Local checks plus optional SafetyCheckerClient.

        Returns:
            (ok, message) - ok is True if command would succeed.
        """
        logger.debug(
            f"can_goto: checking target=({target.lat:.6f},{target.lon:.6f}) tol={tolerance}m",
        )
        if not (MIN_POSITION_TOLERANCE_M <= tolerance <= MAX_POSITION_TOLERANCE_M):
            return False, (f"Tolerance must be between {MIN_POSITION_TOLERANCE_M} and {MAX_POSITION_TOLERANCE_M}m")
        if self.safety is not None:
            ok, msg = await self.safety.validate_waypoint(self.position, target)
            logger.debug(f"can_goto: safety check ok={ok} msg={msg!r}")
            if not ok:
                return False, msg
        logger.debug("can_goto: passed")
        return True, ""

    async def can_land(self) -> tuple[bool, str]:
        """
        Check if land would succeed. Optional SafetyCheckerClient only.

        Returns:
            (ok, message) - ok is True if command would succeed.
        """
        logger.debug(
            f"can_land: checking pos=({self.position.lat:.6f},{self.position.lon:.6f})",
        )
        if self.safety is not None:
            ok, msg = await self.safety.validate_landing(
                self.position.lat,
                self.position.lon,
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
        mavsdk_server_port: int = DEFAULT_MAVSDK_SERVER_PORT,
        *,
        timeout: float = CONNECTION_TIMEOUT_S,
        safety: Any | None = None,
        aerpaw_platform: Any | None = None,
    ) -> Vehicle:
        """Connect to vehicle and start telemetry.

        Args:
            connection_string: MAVLink connection string (e.g. ``udp://:14550``).
            mavsdk_server_port: gRPC port for the mavsdk_server process.
            timeout: Connection timeout in seconds.
            safety: SafetyCheckerClient or NoOpSafetyChecker. None disables
                safety checks in can_takeoff/can_goto/can_land.
            aerpaw_platform: AerpawPlatform instance for AERPAW environment integration.
                    None disables AERPAW platform notifications.

        Returns:
            Initialised and connected Vehicle instance with telemetry running.

        Raises:
            ConnectionTimeoutError: If no heartbeat is received within timeout.
        """
        logger.info(
            f"Connecting to vehicle at {connection_string} (port={mavsdk_server_port}, timeout={timeout}s)",
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
            """Block until MAVSDK reports an active connection state."""
            async for state in system.core.connection_state():
                if state.is_connected:
                    return

        try:
            await asyncio.wait_for(_wait_for_heartbeat(), timeout=timeout)
        except asyncio.TimeoutError as e:
            logger.error(f"Connection timeout: no heartbeat within {timeout}s")
            raise ConnectionTimeoutError(
                timeout,
                "Connection established but no heartbeat within timeout",
            ) from e

        # Create instance and start telemetry
        self = cls(
            system,
            connection_string,
            mavsdk_server_port,
            safety=safety,
            aerpaw_platform=aerpaw_platform,
        )
        await self._start_telemetry()
        self._connection.set_link_alive(True)
        self._connection.record_telemetry()
        logger.info("Vehicle connected and telemetry started")
        return self

    async def _start_telemetry(self) -> None:
        """Start telemetry subscriptions on same loop."""
        logger.debug(
            "Starting telemetry subscriptions (position, attitude, velocity, gps, battery, mode, armed, health, home)",
        )

        # Throttle interval for periodic telemetry debug logs (seconds)
        _telem_log_interval = 5.0
        last_struct_telem = [0.0]

        def _telem_log_throttle(
            last: list,
            interval: float = _telem_log_interval,
        ) -> bool:
            """Return True if we should log (throttled). Mutates last[0]."""
            now = time.monotonic()
            if last[0] == 0 or (now - last[0]) >= interval:
                last[0] = now
                return True
            return False

        async def _position_update() -> None:
            """Subscribe to position telemetry and refresh shared vehicle state."""
            first = [True]
            last_log = [0.0]
            async for position in self._system.telemetry.position():
                if self._connection.closed:
                    return
                self._state.update_position(
                    position.latitude_deg,
                    position.longitude_deg,
                    position.relative_altitude_m,
                    position.absolute_altitude_m,
                )
                from aerpawlib.cli.progress_bar import update_telemetry

                update_telemetry(altitude=position.relative_altitude_m)
                self._connection.record_telemetry()
                if first[0]:
                    logger.info(
                        f"Telemetry: position stream active (lat={position.latitude_deg:.6f}, lon={position.longitude_deg:.6f}, alt={position.relative_altitude_m:.1f}m)",
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: position lat={position.latitude_deg:.6f} lon={position.longitude_deg:.6f} alt={position.relative_altitude_m:.1f}m",
                    )
                if self._event_log and _telem_log_throttle(last_struct_telem):
                    self._log_structured_telemetry_snapshot()

        async def _attitude_update() -> None:
            """Subscribe to attitude telemetry and convert degrees to radians."""
            first = [True]
            last_log = [0.0]
            async for att in self._system.telemetry.attitude_euler():
                if self._connection.closed:
                    return
                self._state.update_attitude(
                    math.radians(att.roll_deg),
                    math.radians(att.pitch_deg),
                    math.radians(att.yaw_deg),
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: attitude stream active (roll={att.roll_deg:.1f} pitch={att.pitch_deg:.1f} yaw={att.yaw_deg:.1f} deg)",
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: attitude roll={att.roll_deg:.1f} pitch={att.pitch_deg:.1f} yaw={att.yaw_deg:.1f} deg",
                    )

        async def _velocity_update() -> None:
            """Subscribe to NED velocity telemetry."""
            first = [True]
            last_log = [0.0]
            async for vel in self._system.telemetry.velocity_ned():
                if self._connection.closed:
                    return
                self._state.update_velocity(vel.north_m_s, vel.east_m_s, vel.down_m_s)
                if first[0]:
                    logger.info(
                        f"Telemetry: velocity stream active (N={vel.north_m_s:.2f} E={vel.east_m_s:.2f} D={vel.down_m_s:.2f} m/s)",
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: velocity N={vel.north_m_s:.2f} E={vel.east_m_s:.2f} D={vel.down_m_s:.2f} m/s",
                    )

        async def _gps_update() -> None:
            """Subscribe to GPS fix telemetry and keep compatibility with enums/ints."""
            first = [True]
            last_log = [0.0]
            async for gps in self._system.telemetry.gps_info():
                if self._connection.closed:
                    return
                fix = gps.fix_type.value if hasattr(gps.fix_type, "value") else gps.fix_type
                self._state.update_gps(fix, gps.num_satellites)
                from aerpawlib.cli.progress_bar import update_telemetry

                update_telemetry(sats=gps.num_satellites)
                if first[0]:
                    logger.info(
                        f"Telemetry: gps stream active (fix_type={fix}, sats={gps.num_satellites})",
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: gps fix_type={fix} sats={gps.num_satellites}",
                    )

        async def _battery_update() -> None:
            """Subscribe to battery telemetry and normalize optional current values."""
            first = [True]
            last_log = [0.0]
            async for bat in self._system.telemetry.battery():
                if self._connection.closed:
                    return
                current = getattr(bat, "current_battery_a", 0.0) or 0.0
                self._state.update_battery(
                    bat.voltage_v,
                    current,
                    int(bat.remaining_percent),
                )
                from aerpawlib.cli.progress_bar import update_telemetry

                update_telemetry(battery=int(bat.remaining_percent))
                if first[0]:
                    logger.info(
                        f"Telemetry: battery stream active ({bat.voltage_v:.1f}V, {int(bat.remaining_percent)}%)",
                    )
                    first[0] = False
                elif _telem_log_throttle(last_log):
                    logger.debug(
                        f"Telemetry: battery {bat.voltage_v:.1f}V {current:.1f}A {int(bat.remaining_percent)}%",
                    )

        async def _flight_mode_update() -> None:
            """Subscribe to flight-mode updates and emit change logs."""
            first = [True]
            prev_mode: list = [None]
            async for mode in self._system.telemetry.flight_mode():
                if self._connection.closed:
                    return
                mode_name = mode.name
                self._state.update_mode(mode_name)
                from aerpawlib.cli.progress_bar import update_telemetry

                update_telemetry(mode=mode_name)
                if first[0]:
                    logger.info(
                        f"Telemetry: flight_mode stream active (mode={mode_name})",
                    )
                    first[0] = False
                    prev_mode[0] = mode_name
                elif prev_mode[0] != mode_name:
                    logger.info(
                        f"Telemetry: flight_mode changed {prev_mode[0]} -> {mode_name}",
                    )
                    prev_mode[0] = mode_name

        async def _armed_update() -> None:
            """Subscribe to armed state and detect unexpected disarm transitions."""
            first = [True]
            prev_armed: list = [None]
            async for armed in self._system.telemetry.armed():
                if self._connection.closed:
                    return
                self._state.update_armed(armed)
                from aerpawlib.cli.progress_bar import update_telemetry

                update_telemetry(armed=armed)
                if first[0]:
                    logger.info(f"Telemetry: armed stream active (armed={armed})")
                    first[0] = False
                    prev_armed[0] = armed
                elif prev_armed[0] != armed:
                    logger.info(f"Telemetry: armed changed {prev_armed[0]} -> {armed}")
                    if self._event_log:
                        self._event_log.log_event("arm" if armed else "disarm")
                    if prev_armed[0] is True and not armed and not self._expecting_disarm:
                        logger.warning(
                            "Vehicle disarmed unexpectedly! Signalling experiment termination.",
                        )
                        self._unexpected_disarm_event.set()
                    prev_armed[0] = armed

        async def _health_update() -> None:
            """Subscribe to health telemetry and update aggregate armability flags."""
            first = [True]
            async for health in self._system.telemetry.health():
                if self._connection.closed:
                    return
                self._state.update_armable(
                    health.is_global_position_ok,
                    health.is_local_position_ok,
                    health.is_home_position_ok,
                    health.is_armable,
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: health stream active (armable={health.is_armable})",
                    )
                    first[0] = False

        async def _home_update() -> None:
            """Subscribe to home-position telemetry for relative-altitude commands."""
            first = [True]
            async for home in self._system.telemetry.home():
                if self._connection.closed:
                    return
                self._state.update_home(
                    home.latitude_deg,
                    home.longitude_deg,
                    home.relative_altitude_m,
                    home.absolute_altitude_m,
                )
                if first[0]:
                    logger.info(
                        f"Telemetry: home stream active (lat={home.latitude_deg:.6f} lon={home.longitude_deg:.6f} alt={home.relative_altitude_m:.1f}m)",
                    )
                    first[0] = False

        async def _mavlink_status_update() -> None:
            """Subscribe to SYS_STATUS to capture pre-arm bitmask readiness."""
            async for msg in self._system.mavlink_direct.message("SYS_STATUS"):
                if self._connection.closed:
                    return
                try:
                    fields = json.loads(msg.fields_json)
                    health = fields.get("onboard_control_sensors_health", 0)
                    self._state.update_prearm_bits(
                        (health & MAV_SYS_STATUS_PREARM_CHECK) == MAV_SYS_STATUS_PREARM_CHECK,
                    )
                except Exception as e:
                    logger.debug(f"Error parsing SYS_STATUS: {e}")

        async def _ekf_status_update() -> None:
            """Subscribe to EKF_STATUS_REPORT (ArduPilot) for takeoff readiness."""
            try:
                async for msg in self._system.mavlink_direct.message(
                    "EKF_STATUS_REPORT",
                ):
                    if self._connection.closed:
                        return
                    try:
                        fields = json.loads(msg.fields_json)
                        flags = fields.get("flags", 0)
                        self._state.update_ekf_from_flags(flags)
                    except Exception as e:
                        logger.debug(f"Error parsing EKF_STATUS_REPORT: {e}")
            except Exception as e:
                logger.debug(
                    "EKF_STATUS_REPORT subscription not available (e.g. PX4): %s",
                    e,
                )

        async def _connection_state_update() -> None:
            """Track MAVSDK connection state to mirror heartbeat availability."""
            async for state in self._system.core.connection_state():
                if self._connection.closed:
                    return
                if state.is_connected:
                    if not self._connection.link_alive:
                        logger.info("Vehicle connection restored")
                    self._connection.set_link_alive(True)
                else:
                    if self._connection.link_alive:
                        logger.warning(
                            "Vehicle heartbeat lost (MAVSDK reports disconnected)",
                        )
                    self._connection.set_link_alive(False)

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
            _ekf_status_update,
            _connection_state_update,
        ]:
            task = asyncio.create_task(coro())
            self._telemetry_tasks.append(task)
        logger.debug(f"Started {len(self._telemetry_tasks)} telemetry tasks")

    def done_moving(self) -> bool:
        """Return True if the vehicle is ready to accept the next command."""
        return self._ready_to_move(self)

    @property
    def _default_goto_tolerance(self) -> float:
        """Default arrival tolerance in metres for cardinal goto helpers."""
        return DEFAULT_POSITION_TOLERANCE_M

    def _standalone_arm_wait_ekf(self) -> bool:
        """Return True to wait for EKF readiness before standalone auto-arm."""
        return False

    def _vehicle_type_label(self) -> str:
        """Short label for log messages (e.g. 'vehicle', 'rover')."""
        return "vehicle"

    async def _wait_for_armable(self, log_prefix: str = "") -> None:
        """Poll until armable or timeout (used by preflight/initialize)."""
        start = time.monotonic()
        last_log = 0.0
        while not self._state.armable:
            if time.monotonic() - start > ARMABLE_TIMEOUT_S:
                logger.warning(
                    f"{log_prefix}Timeout waiting for armable ({ARMABLE_TIMEOUT_S}s). Status: {self._get_health_summary()}",
                )
                break
            if time.monotonic() - last_log > ARMABLE_STATUS_LOG_INTERVAL_S:
                logger.debug(
                    f"{log_prefix}Waiting for armable... {self._get_health_summary()}",
                )
                last_log = time.monotonic()
            await asyncio.sleep(POLLING_DELAY_S)

    async def _preflight_wait(self, should_arm: bool = True) -> None:
        """Wait for pre-arm conditions. Call before run."""
        self._will_arm = should_arm
        await self._wait_for_armable()

    async def initialize(self, should_arm: bool = True) -> None:
        """Wait for pre-arm conditions before mission start."""
        await self._preflight_wait(should_arm)

    async def _pre_auto_arm(self) -> None:
        """Hook for subclass-specific setup before standalone auto-arm."""

    async def _auto_arm_standalone(self) -> None:
        """Arm in standalone/SITL mode after local preflight checks pass."""
        label = self._vehicle_type_label()
        logger.info(f"Standalone mode: auto-arming {label}...")
        await _wait_for_condition(
            lambda: self._state.armable,
            timeout=CONNECTION_TIMEOUT_S,
            timeout_message=f"{label.capitalize()} not armable: {self._get_health_summary()}",
        )
        await _wait_for_condition(
            lambda: self.gps.fix_type >= GPS_3D_FIX_TYPE,
            timeout=POSITION_READY_TIMEOUT_S,
            timeout_message=f"{label.capitalize()}: no GPS 3D fix",
        )
        if self._standalone_arm_wait_ekf():
            while not self.ekf_ready:
                await asyncio.sleep(POST_ARM_STABILIZE_DELAY_S)
        await self.set_armed(True)
        logger.info(f"{label.capitalize()} armed successfully")

    async def _await_aerpaw_safety_pilot_arm(self) -> None:
        """AERPAW: OEO notice (async), then wait indefinitely for pilot to arm."""
        if not self._aerpaw_platform:
            logger.warning("AERPAW safety pilot arm called but no platform available")
            return
        task = asyncio.create_task(
            self._aerpaw_platform.log_to_oeo_async(
                "[aerpawlib] Guided command attempted. Waiting for safety pilot to arm",
            ),
        )
        self._command_tasks.append(task)
        from aerpawlib.cli.progress_bar import update_progress
        update_progress(state="Waiting for arm...")
        await _wait_for_condition(
            lambda: self._state.armable,
            poll_interval=POLLING_DELAY_S,
        )
        await _wait_for_condition(
            lambda: self.armed,
            poll_interval=POLLING_DELAY_S,
        )
        update_progress(state="")

    async def _arm_vehicle_post_arm_home_wait(self) -> None:
        """Shared tail after vehicle is armed (AERPAW or auto-arm): delay + home."""
        await asyncio.sleep(ARMING_SEQUENCE_DELAY_S)
        await _wait_for_condition(
            lambda: self._state.home_coords is not None,
            timeout=HOME_POSITION_TIMEOUT_S,
            timeout_message="Home position not available",
        )

    async def _arm_vehicle(self) -> None:
        """Arm and prepare for mission. Subclasses may override hooks only."""
        if not self._will_arm:
            logger.debug("Vehicle: _arm_vehicle skipped (_will_arm=False)")
            return
        await self._pre_auto_arm()
        if self._aerpaw_platform and self._aerpaw_platform.is_connected:
            await self._await_aerpaw_safety_pilot_arm()
        else:
            await self._auto_arm_standalone()
        await self._arm_vehicle_post_arm_home_wait()

    async def await_ready_to_move(self) -> None:
        """Wait until vehicle is ready for next command."""
        if self._connection.closed:
            raise RuntimeError("Cannot await_ready_to_move: vehicle is closed")
        if self._will_arm and not self.armed:
            logger.debug("await_ready_to_move: vehicle not armed, running arm sequence")
            await self._arm_vehicle()
        logger.debug("await_ready_to_move: waiting for done_moving")
        start = time.monotonic()
        last_log = 0.0
        while not self.done_moving():
            if self._connection.closed:
                raise RuntimeError("Vehicle closed while waiting for ready_to_move")
            elapsed = time.monotonic() - start
            if elapsed > 300.0:
                raise TimeoutError("Vehicle did not report ready within timeout")
            now = time.monotonic()
            if now - last_log >= READY_MOVE_LOG_INTERVAL_S:
                logger.debug(
                    "await_ready_to_move: still waiting (elapsed=%.0fs mode=%s armed=%s)",
                    elapsed,
                    self.mode,
                    self.armed,
                )
                last_log = now
            await asyncio.sleep(POLLING_DELAY_S)
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
        if self._connection.closed or self._system is None:
            raise RuntimeError("Cannot set_armed: vehicle is closed")
        if value and not self._state.armable:
            logger.warning(f"Arm rejected: {self._get_health_summary()}")
            raise NotArmableError(f"Vehicle not armable: {self._get_health_summary()}")
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
            if value:
                raise ArmError(str(e), original_error=e) from e
            raise DisarmError(str(e), original_error=e) from e
        finally:
            if not value:
                self._expecting_disarm = False

    def _get_health_summary(self) -> str:
        """Return a human-readable summary of current health/GPS/armable status.

        Returns:
            Short string describing GPS fix type, satellites visible, and
            armable flag.
        """
        return f"GPS fix: {self._state.gps.fix_type}, sats: {self._state.gps.satellites_visible}, armable: {self._state.armable}"

    async def _stop(self) -> None:
        """Stop background movement."""
        self._ready_to_move = lambda _: True

    async def set_groundspeed(self, velocity: float) -> None:
        """Set the maximum ground speed of the vehicle.

        Args:
            velocity: Maximum speed in m/s.
        """
        if self._connection.closed or self._system is None:
            raise RuntimeError("Cannot set_groundspeed: vehicle is closed")
        try:
            await self._system.action.set_maximum_speed(velocity)
        except Exception as e:
            logger.warning("set_groundspeed failed: %s", e)

    async def aclose(self) -> None:
        """Async cleanup: cancel tasks, stop movement, release MAVSDK."""
        if self._connection.closed:
            return
        logger.info("Closing vehicle connection (async)")
        self._connection.mark_closed()
        tasks = list(self._telemetry_tasks) + list(self._command_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._stop()
        self._telemetry_tasks.clear()
        self._command_tasks.clear()
        self._system = None
        logger.info("Vehicle connection closed")

    def close(self) -> None:
        """Clean up. Cancels all telemetry and command tasks."""
        if self._connection.closed:
            logger.debug("close() called but already closed")
            return
        logger.info("Closing vehicle connection")
        self._connection.mark_closed()
        for task in getattr(self, "_telemetry_tasks", []):
            task.cancel()
        for task in getattr(self, "_command_tasks", []):
            task.cancel()
        self._telemetry_tasks.clear()
        if hasattr(self, "_command_tasks"):
            self._command_tasks.clear()
        logger.info("Vehicle connection closed")
        self._system = None

    async def goto_north(
        self,
        meters: float,
        tolerance: float | None = None,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Go ``meters`` north from current position."""
        tol = tolerance if tolerance is not None else self._default_goto_tolerance
        return await goto_cardinal(
            self,
            meters,
            0,
            tolerance=tol,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_east(
        self,
        meters: float,
        tolerance: float | None = None,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Go ``meters`` east from current position."""
        tol = tolerance if tolerance is not None else self._default_goto_tolerance
        return await goto_cardinal(
            self,
            0,
            meters,
            tolerance=tol,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_south(
        self,
        meters: float,
        tolerance: float | None = None,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Go ``meters`` south from current position."""
        tol = tolerance if tolerance is not None else self._default_goto_tolerance
        return await goto_cardinal(
            self,
            -meters,
            0,
            tolerance=tol,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_west(
        self,
        meters: float,
        tolerance: float | None = None,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Go ``meters`` west from current position."""
        tol = tolerance if tolerance is not None else self._default_goto_tolerance
        return await goto_cardinal(
            self,
            0,
            -meters,
            tolerance=tol,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_ned(
        self,
        north: float,
        east: float,
        down: float = 0,
        tolerance: float | None = None,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Go by NED offset from current position."""
        tol = tolerance if tolerance is not None else self._default_goto_tolerance
        return await goto_offset(
            self,
            north,
            east,
            down,
            tolerance=tol,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_bearing(
        self,
        bearing_deg: float,
        distance_m: float,
        tolerance: float | None = None,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Navigate along a bearing for a ground distance."""
        tol = tolerance if tolerance is not None else self._default_goto_tolerance
        return await goto_bearing_distance(
            self,
            bearing_deg,
            distance_m,
            tolerance=tol,
            target_heading=target_heading,
            timeout=timeout,
            blocking=blocking,
        )

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = 2.0,
        target_heading: float | None = None,
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

    def __init__(self, *, safety: Any | None = None) -> None:
        """Initialise a no-op vehicle with default state suitable for dry-runs.

        Args:
            safety: Optional safety checker; defaults to None (no safety checks).
        """
        super().__init__(
            system=None,  # type: ignore[arg-type]
            connection_string="",
            mavsdk_server_port=DEFAULT_MAVSDK_SERVER_PORT,
            safety=safety,
        )
        self._state = default_mock_state()
        self._connection.set_link_alive(True)
        self._connection.record_telemetry()
        self._will_arm = False

    async def _arm_vehicle(self) -> None:
        """Dry-run: no MAVSDK arming."""
        if not self._will_arm:
            logger.debug("DummyVehicle: _arm_vehicle skipped (_will_arm=False)")
            return

    @classmethod
    async def connect(
        cls,
        connection_string: str = "",
        mavsdk_server_port: int = DEFAULT_MAVSDK_SERVER_PORT,
        *,
        timeout: float = CONNECTION_TIMEOUT_S,
        safety: Any | None = None,
        aerpaw_platform: Any | None = None,
    ) -> DummyVehicle:
        """Return a DummyVehicle without opening any real connection.

        Args:
            connection_string: Ignored.
            mavsdk_server_port: Ignored.
            timeout: Ignored.
            safety: Passed to the DummyVehicle constructor.
            aerpaw_platform: Ignored.

        Returns:
            A new DummyVehicle instance.
        """
        return cls(safety=safety)

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = 2.0,
        target_heading: float | None = None,
    ) -> None:
        """No-op for dry-run."""
        pass

    def close(self) -> None:
        """Mark the dummy vehicle as closed without external side effects."""
        self._connection.mark_closed()

    def watch_disconnect(
        self,
        timeout: float,
        *,
        on_disconnect: Callable[[], None] | None = None,
    ) -> asyncio.Future:
        """No-op disconnect watch for dry-run vehicles."""
        loop = asyncio.get_running_loop()
        return loop.create_future()
