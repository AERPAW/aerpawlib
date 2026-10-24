"""MAVSDK telemetry subscription setup for v1 vehicles (private)."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aerpawlib._internal.mavlink_ids import autopilot_sysid
from aerpawlib.cli.progress_bar import update_telemetry
from aerpawlib.v1 import util
from aerpawlib.v1.constants import EKF_READY_FLAGS, MAV_SYS_STATUS_PREARM_CHECK, MAX_TELEMETRY_RETRIES
from aerpawlib.v1.log import LogComponent, get_logger
from aerpawlib.v1.vehicle.state import InitPhase
from aerpawlib.v1.vehicle.telemetry_compat import (
    _AttitudeCompat,
    _BatteryCompat,
    _GPSInfoCompat,
)

if TYPE_CHECKING:
    from aerpawlib.v1.vehicle.core_vehicle import Vehicle

logger = get_logger(LogComponent.VEHICLE)


# Streams whose loss means the vehicle cannot be trusted as connected.
_CRITICAL_STREAMS = ("position", "armed", "connection")
# Pause before re-subscribing after a stream ends or fails (never busy-spin).
_STREAM_RESTART_DELAY_S = 1.0
_STREAM_MAX_BACKOFF_S = 5.0
# A stream that ran this long before failing was healthy: reset its retries.
_STREAM_HEALTHY_RESET_S = 10.0


def _dead_streams(vehicle: Vehicle) -> set:
    dead = getattr(vehicle, "_dead_telemetry_streams", None)
    if dead is None:
        dead = set()
        vehicle._dead_telemetry_streams = dead
    return dead


def _mark_stream_alive(vehicle: Vehicle, name: str) -> None:
    """Called per sample of a critical stream; restores connected on recovery."""
    dead = _dead_streams(vehicle)
    if name not in dead:
        return
    dead.discard(name)
    logger.info("Telemetry stream '%s' recovered", name)
    if not dead and getattr(vehicle, "_link_connected", False) and not vehicle._lifecycle.closed:
        vehicle._lifecycle.has_heartbeat = True


async def resilient_telemetry_task(
    vehicle: Vehicle,
    name: str,
    coro_factory: Callable[[], Any],
) -> None:
    """Wrap a telemetry subscription in retry logic.

    A stream that ends is re-subscribed after a delay. A failing stream backs
    off; non-critical streams give up after ``MAX_TELEMETRY_RETRIES``
    consecutive failures. Critical streams keep retrying, and after that many
    failures the vehicle is reported disconnected until the stream recovers.
    """
    retry_count = 0
    max_retries = MAX_TELEMETRY_RETRIES
    critical = name in _CRITICAL_STREAMS
    while vehicle._lifecycle.is_running():
        started = time.monotonic()
        try:
            await coro_factory()
            delay = _STREAM_RESTART_DELAY_S
        except asyncio.CancelledError:
            return
        except Exception as e:
            if not vehicle._lifecycle.is_running():
                return
            if time.monotonic() - started >= _STREAM_HEALTHY_RESET_S:
                retry_count = 0
            retry_count += 1
            logger.warning(
                f"Telemetry stream '{name}' failed (attempt {retry_count}): {e}",
            )
            if retry_count >= max_retries:
                if not critical:
                    logger.error(
                        f"Telemetry stream '{name}' failed after {max_retries} retries",
                    )
                    return
                _dead_streams(vehicle).add(name)
                if vehicle._lifecycle.has_heartbeat:
                    logger.warning(
                        "Critical telemetry stream '%s' keeps failing; marking vehicle as disconnected until it recovers",
                        name,
                    )
                    vehicle._lifecycle.has_heartbeat = False
            delay = min(float(retry_count), _STREAM_MAX_BACKOFF_S)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return


async def start_telemetry(vehicle: Vehicle) -> None:
    """Spawn background tasks to subscribe to telemetry streams."""

    async def _position_update() -> None:
        async for position in vehicle._system.telemetry.position():
            vehicle._ts_state.position_lat.set(position.latitude_deg)
            vehicle._ts_state.position_lon.set(position.longitude_deg)
            vehicle._ts_state.position_alt.set(position.relative_altitude_m)
            vehicle._ts_state.position_abs_alt.set(position.absolute_altitude_m)
            update_telemetry(altitude=position.relative_altitude_m)
            _mark_stream_alive(vehicle, "position")

    async def _attitude_update() -> None:
        async for attitude in vehicle._system.telemetry.attitude_euler():
            new_att = _AttitudeCompat()
            new_att.roll = math.radians(attitude.roll_deg)
            new_att.pitch = math.radians(attitude.pitch_deg)
            new_att.yaw = math.radians(attitude.yaw_deg)
            vehicle._ts_state.attitude_val.set(new_att)
            vehicle._ts_state.heading_deg.set(attitude.yaw_deg % 360)
            update_telemetry(heading=attitude.yaw_deg)

    async def _velocity_update() -> None:
        async for velocity in vehicle._system.telemetry.velocity_ned():
            vehicle._ts_state.velocity_ned.set(
                [velocity.north_m_s, velocity.east_m_s, velocity.down_m_s],
            )
            update_telemetry(
                velocity_ned=(
                    velocity.north_m_s,
                    velocity.east_m_s,
                    velocity.down_m_s,
                ),
            )

    async def _gps_update() -> None:
        async for gps_info in vehicle._system.telemetry.gps_info():
            new_gps = _GPSInfoCompat()
            new_gps.satellites_visible = gps_info.num_satellites
            new_gps.fix_type = gps_info.fix_type.value
            vehicle._ts_state.gps_val.set(new_gps)
            update_telemetry(
                sats=gps_info.num_satellites,
                gps_fix=gps_info.fix_type.value,
            )

    async def _battery_update() -> None:
        async for battery in vehicle._system.telemetry.battery():
            remaining = battery.remaining_percent
            if remaining is None or not math.isfinite(remaining):
                logger.debug(f"Telemetry: skipping non-finite battery sample ({remaining!r})")
                continue
            new_bat = _BatteryCompat()
            new_bat.voltage = battery.voltage_v
            new_bat.current = battery.current_battery_a
            new_bat.level = int(battery.remaining_percent)
            vehicle._ts_state.battery_val.set(new_bat)
            update_telemetry(
                battery=int(battery.remaining_percent),
                voltage=battery.voltage_v,
            )

    async def _flight_mode_update() -> None:
        async for mode in vehicle._system.telemetry.flight_mode():
            vehicle._ts_state.mode.set(mode.name)
            update_telemetry(mode=mode.name)

    async def _armed_update() -> None:
        async for armed in vehicle._system.telemetry.armed():
            old_armed = vehicle._ts_state.armed_state.get()
            vehicle._ts_state.armed_state.set(armed)
            vehicle._ts_state.armed_telemetry_received.set(True)
            update_telemetry(armed=armed)
            _mark_stream_alive(vehicle, "armed")
            if armed and not old_armed:
                vehicle._ts_state.last_arm_time.set(time.time())
            elif old_armed and not armed:
                vehicle._init_phase = InitPhase.PENDING

    async def _health_update() -> None:
        async for health in vehicle._system.telemetry.health():
            vehicle._ts_state.health_val.set(health)
            # Do not require health.is_armable / SYS_STATUS PREARM: MAVSDK maps
            # that PX4 bit and it stays false on ArduPilot even when ARM works.
            vehicle._ts_state.is_armable_state.set(
                health.is_global_position_ok and health.is_local_position_ok and health.is_home_position_ok,
            )

    async def _mavlink_status_update() -> None:
        async for msg in vehicle._system.mavlink_direct.message("SYS_STATUS"):
            sysid = autopilot_sysid(msg)
            if sysid:
                vehicle._ts_state.autopilot_sysid.set(sysid)
            try:
                fields = json.loads(msg.fields_json)
                health = fields.get("onboard_control_sensors_health", 0)
                vehicle._ts_state.prearm_checks_ok.set(
                    (health & MAV_SYS_STATUS_PREARM_CHECK) == MAV_SYS_STATUS_PREARM_CHECK,
                )
            except Exception as e:
                logger.debug(f"Error parsing SYS_STATUS: {e}")

    async def _ekf_status_update() -> None:
        # Subscription errors propagate so resilient_telemetry_task backs off
        # and eventually gives up (e.g. PX4 has no EKF_STATUS_REPORT);
        # swallowing them here re-subscribed in a tight loop.
        async for msg in vehicle._system.mavlink_direct.message(
            "EKF_STATUS_REPORT",
        ):
            try:
                fields = json.loads(msg.fields_json)
                flags = fields.get("flags", 0)
                vehicle._ts_state.ekf_ready.set(
                    (flags & EKF_READY_FLAGS) == EKF_READY_FLAGS,
                )
            except Exception as e:
                logger.debug(f"Error parsing EKF_STATUS_REPORT: {e}")

    async def _home_update() -> None:
        async for home in vehicle._system.telemetry.home():
            vehicle._ts_state.home_position.set(
                util.Coordinate(
                    home.latitude_deg,
                    home.longitude_deg,
                    home.relative_altitude_m,
                ),
            )
            vehicle._ts_state.home_abs_alt.set(home.absolute_altitude_m)

    async def _connection_state_update() -> None:
        async for state in vehicle._system.core.connection_state():
            _mark_stream_alive(vehicle, "connection")
            vehicle._link_connected = state.is_connected
            if state.is_connected:
                dead = _dead_streams(vehicle)
                if dead:
                    logger.debug("Link up but telemetry streams %s are down; not reporting connected", sorted(dead))
                elif not vehicle._lifecycle.has_heartbeat:
                    logger.info("Vehicle connection restored")
                    vehicle._lifecycle.has_heartbeat = True
            elif vehicle._lifecycle.has_heartbeat:
                logger.warning(
                    "Vehicle heartbeat lost (MAVSDK reports disconnected)",
                )
                vehicle._lifecycle.has_heartbeat = False

    telemetry_defs = [
        ("position", lambda: _position_update()),
        ("attitude", lambda: _attitude_update()),
        ("velocity", lambda: _velocity_update()),
        ("gps", lambda: _gps_update()),
        ("battery", lambda: _battery_update()),
        ("flight_mode", lambda: _flight_mode_update()),
        ("armed", lambda: _armed_update()),
        ("health", lambda: _health_update()),
        ("mavlink_status", lambda: _mavlink_status_update()),
        ("ekf_status", lambda: _ekf_status_update()),
        ("home", lambda: _home_update()),
        ("connection", lambda: _connection_state_update()),
    ]

    for name, factory in telemetry_defs:
        task = asyncio.create_task(
            resilient_telemetry_task(vehicle, name, factory),
        )
        vehicle._telemetry_tasks.append(task)


async def fetch_vehicle_info(vehicle: Vehicle) -> None:
    """Fetch static vehicle information like firmware version once."""
    try:
        version = await vehicle._system.info.get_version()
        vehicle._autopilot_info.major = version.flight_sw_major
        vehicle._autopilot_info.minor = version.flight_sw_minor
        vehicle._autopilot_info.patch = version.flight_sw_patch
    except Exception as e:
        logger.debug("Could not fetch vehicle version info: %s", e)
