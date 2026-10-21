"""MAVSDK-backed multirotor implementation for the v2 API.

See ``aerpawlib.v2.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from mavsdk.action import ActionError

from aerpawlib.v2.constants import (
    COPTER_GUIDED_MODE,
    COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
    DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    HEADING_TOLERANCE_DEG,
    MIN_ARM_TO_TAKEOFF_DELAY_S,
    POLLING_DELAY_S,
    POST_TAKEOFF_STABILIZATION_S,
    TAKEOFF_LOG_INTERVAL_S,
)
from aerpawlib.v2.exceptions import (
    LandingError,
    NavigationError,
    RTLError,
    TakeoffError,
)
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.types import Coordinate, VectorNED

from .base import Vehicle, _invalid_takeoff_altitude, _wait_for_condition
from .connection_helpers import _validate_tolerance
from .heading import _heading_diff, _normalize_heading
from .navigation import start_nonblocking_goto, wait_for_blocking_goto
from .task import VehicleTask

logger = get_logger(LogComponent.DRONE)

# Horizontal moves shorter than this have no meaningful bearing.
_COINCIDENT_DISTANCE_M = 0.01
# Arrival checks altitude separately from the horizontal tolerance, with at
# least this much vertical slack.
_ARRIVAL_MIN_ALT_TOLERANCE_M = 3.0
# return_to_launch only lands in place after a failed home goto when this
# close to home (the C-VM filter rejects a land > 5 m from the pad).
_RTL_LAND_IN_PLACE_MAX_M = 5.0


class Drone(Vehicle):
    """Drone implementation for multirotors."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise the Drone, forwarding all arguments to Vehicle."""
        super().__init__(*args, **kwargs)
        self._current_heading: float | None = None

    def _standalone_arm_wait_ekf(self) -> bool:
        return True

    async def _pre_auto_arm(self) -> None:
        """ArduCopter auto-disarms if armed in STABILIZE without RC. Enter GUIDED first."""
        await self._set_guided_mode()

    async def set_heading(
        self,
        heading: float | None,
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """Command the drone to face a given heading.

        Args:
            heading: Target heading in degrees (0-360). Pass None to clear
                the currently locked heading.
            blocking: If True (default), wait until the heading is reached
                before returning. A blocking turn ends a running set_velocity.
            lock_in: If True (default), store the heading so subsequent
                goto_coordinates commands maintain it.

        Raises:
            NavigationError: If the heading is not finite, the yaw command
                cannot be sent, or the turn does not finish in time. The
                previous heading lock is kept and the vehicle is marked idle.
        """
        if heading is not None and not math.isfinite(heading):
            raise NavigationError(f"set_heading: heading must be finite (got {heading!r})")
        if blocking:
            await self.await_ready_to_move()
        if heading is None:
            logger.debug("Drone: set_heading(None) clearing heading lock")
            self._current_heading = None
            return
        heading = _normalize_heading(heading)
        logger.debug(f"Drone: set_heading({heading:.1f} deg) blocking={blocking}")
        previous_lock = self._current_heading
        if lock_in:
            self._current_heading = heading
        if not blocking:
            # A running set_velocity keeps its yaw; the lock applies to the next one.
            return
        # The velocity stream would keep overriding the yaw: stop and turn.
        await self._stop_velocity()
        gen = self._begin_move()
        try:
            from aerpawlib._internal.mavlink_ids import (
                make_condition_yaw_message,
                resolve_mav_sysid,
            )

            sysid = resolve_mav_sysid(self._system)
            msg = make_condition_yaw_message(sysid, heading)
            await self._system.mavlink_direct.send_message(msg)
            self._set_move_gate(gen, lambda s: _heading_diff(heading, s.heading) <= HEADING_TOLERANCE_DEG)
            await _wait_for_condition(
                lambda: self.done_moving(),
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message=f"turn to {heading:.1f} deg timed out after {DEFAULT_GOTO_TIMEOUT_S:.0f}s (heading={self.heading:.1f} deg)",
            )
        except Exception as e:
            logger.warning(f"set_heading error: {e}")
            self._release_move_gate(gen)
            if lock_in:
                self._current_heading = previous_lock
            raise NavigationError(f"set_heading({heading:.1f}) failed: {e}", original_error=e) from e
        else:
            logger.debug(f"Drone: set_heading complete (heading={heading:.1f} deg)")

    async def takeoff(
        self,
        altitude: float,
        min_alt_tolerance: float = DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    ) -> None:
        """Command the drone to take off to the given altitude.

        Args:
            altitude: Target relative altitude in metres above the home point.
            min_alt_tolerance: Fraction of the target altitude that must be
                reached before takeoff is considered complete (default 0.95).

        Raises:
            TakeoffError: If the altitude is not a finite value > 0, or the
                MAVSDK takeoff command fails or times out.

        Note:
            Verified on MAVSDK 3.17.x as COMMAND_LONG NAV_TAKEOFF (22) with
            altitude in param7. The AERPAW copter filter still reads takeoff
            altitude from param7, not COMMAND_INT ``z``.
        """
        if self._event_log:
            self._event_log.log_event(
                "command",
                type="takeoff",
                arguments={"altitude": altitude},
            )
        bad_alt = _invalid_takeoff_altitude(altitude)
        if bad_alt:
            raise TakeoffError(bad_alt)
        if not (isinstance(min_alt_tolerance, (int, float)) and 0 < min_alt_tolerance <= 1):
            raise TakeoffError(f"min_alt_tolerance must be in (0, 1] (got {min_alt_tolerance!r})")
        try:
            await self._await_preflight_for_takeoff()
        except TimeoutError as e:
            raise TakeoffError(str(e)) from e
        await self._require_can(self.can_takeoff(altitude), "takeoff", TakeoffError)
        await self.await_ready_to_move()
        await self._stop_velocity()
        time_since_arm = time.monotonic() - self._state.last_arm_time
        if time_since_arm < MIN_ARM_TO_TAKEOFF_DELAY_S:
            delay = MIN_ARM_TO_TAKEOFF_DELAY_S - time_since_arm
            logger.debug(f"Drone: takeoff awaiting min arm delay ({delay:.1f}s)")
            await asyncio.sleep(delay)  # Justified: min arm-to-takeoff delay
        if self._mission_start_time is None:
            self._mission_start_time = time.time()
        from aerpawlib.cli.progress_bar import update_progress

        gen = self._begin_move()
        ok = False
        try:
            update_progress(state="Taking off")
            logger.debug(
                "Drone: takeoff sending set_takeoff_altitude(%.1fm) and takeoff()",
                altitude,
            )
            await self._system.action.set_takeoff_altitude(altitude)
            await self._system.action.takeoff()
            # Non-finite altitude samples never count as reached.
            self._set_move_gate(
                gen,
                lambda s: math.isfinite(s.position.alt) and s.position.alt >= altitude * min_alt_tolerance,
            )
            last_log = 0.0
            climb_start = time.monotonic()
            while not self.done_moving():
                if time.monotonic() - climb_start > DEFAULT_GOTO_TIMEOUT_S:
                    raise TakeoffError(
                        f"Takeoff timed out after {DEFAULT_GOTO_TIMEOUT_S:.0f}s (alt={self.position.alt:.1f}m, target={altitude:.1f}m)",
                    )
                now = time.monotonic()
                if now - last_log >= TAKEOFF_LOG_INTERVAL_S:
                    logger.debug(
                        "Drone: takeoff climbing alt=%.1fm target=%.1fm",
                        self.position.alt,
                        altitude,
                    )
                    last_log = now
                await asyncio.sleep(POLLING_DELAY_S)
            await asyncio.sleep(
                POST_TAKEOFF_STABILIZATION_S,
            )  # Justified: stabilization
            if self._event_log:
                self._event_log.log_event(
                    "takeoff",
                    altitude=altitude,
                    lat=self.position.lat,
                    lon=self.position.lon,
                )
            ok = True
        except ActionError as e:
            logger.error(f"Drone: takeoff failed: {e}")
            err_msg = f"Takeoff failed: {e}"
            if self.armed:
                err_msg += " (drone is already armed)"
            raise TakeoffError(err_msg, original_error=e) from e
        finally:
            if not ok:
                self._release_move_gate(gen)
            update_progress(state="")

    async def land(self) -> None:
        """Command the drone to land and wait for disarm.

        Raises:
            LandingError: If the land command fails or times out.

        Note:
            Verified on MAVSDK 3.17.x as COMMAND_LONG NAV_LAND (21). This is
            in-place land, not RTL mode; fly to the takeoff pad first.

            Land does not wait for a previous goto/takeoff/turn to finish; it
            preempts it. The vehicle stays busy until it disarms.
        """
        if self._event_log:
            self._event_log.log_event("command", type="land")
        await self._require_can(self.can_land(), "land", LandingError)
        if self._connection.closed:
            raise RuntimeError("Cannot land: vehicle is closed")
        if self._will_arm and not self.armed:
            await self._arm_vehicle()
        await self._stop_velocity()
        if self._event_log:
            self._event_log.log_event("land_start")
        from aerpawlib.cli.progress_bar import update_progress

        gen = self._begin_move()
        try:
            update_progress(state="Landing")
            logger.debug("Drone: land sending land() command")
            await self._system.action.land()
            self._expecting_disarm = True
            await _wait_for_condition(
                lambda: not self.armed,
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message="Drone: land timed out waiting for disarm",
            )
            if self._event_log:
                self._event_log.log_event("land_complete")
        except (ActionError, TimeoutError) as e:
            logger.error(f"Drone: land failed: {e}")
            raise LandingError(str(e), original_error=e) from e
        finally:
            self._release_move_gate(gen)
            self._expecting_disarm = False
            update_progress(state="")

    async def return_to_launch(self) -> None:
        """Fly to home coordinates and land (RTL mode is not used).

        Raises:
            RTLError: If returning home or landing fails.
        """
        home = self.home_coords
        if home is None:
            logger.error("Drone: return_to_launch requires home coordinates")
            raise RTLError("Home coordinates are not available for return_to_launch")
        if self._event_log:
            self._event_log.log_event("command", type="return_to_launch")
        from aerpawlib.cli.progress_bar import update_progress

        dest = Coordinate(home.lat, home.lon, self.position.alt)
        try:
            update_progress(state="Returning home")
            logger.debug("Drone: return_to_launch navigating home then landing")
            try:
                await self.goto_coordinates(dest)
            except NavigationError as e:
                away = self.position.ground_distance(home)
                if away > _RTL_LAND_IN_PLACE_MAX_M:
                    # Landing here would be off the pad; stay in GUIDED.
                    raise RTLError(
                        f"could not navigate home ({e}); {away:.1f} m from home, not landing away from the pad",
                        original_error=e,
                    ) from e
                logger.warning("Could not navigate home for RTL (%s); %.1f m from home, landing", e, away)
            await self.land()
        except (NavigationError, LandingError, TimeoutError) as e:
            logger.error(f"Drone: return_to_launch failed: {e}")
            raise RTLError(str(e), original_error=e) from e
        finally:
            update_progress(state="")

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Fly to the given coordinates.

        Args:
            coordinates: Target position (lat, lon, relative alt in metres).
            tolerance: Arrival radius in metres (default 2 m).
            target_heading: Optional heading to face before navigating.
            timeout: Maximum seconds to wait when blocking (default 300 s).
            blocking: If True (default), await arrival before returning.
                If False, return a VehicleTask handle immediately.

        Returns:
            None when blocking=True; a VehicleTask handle when blocking=False.

        Raises:
            NavigationError: If the target is not finite, there is no position
                fix or known home AMSL yet, the goto_location MAVSDK call
                fails, or (blocking=True) the drone does not arrive within
                timeout or the link drops.

        Note:
            Verified on MAVSDK 3.17.x as COMMAND_INT DO_REPOSITION (192) with
            lat/lon/alt in x/y/z. Do not switch this to MISSION_ITEM_INT or
            position SET_POSITION_TARGET; the 2026 copter filter rejects those.
        """
        if self._event_log:
            self._event_log.log_event(
                "command",
                type="goto_coordinates",
                arguments={
                    "target_lat": coordinates.lat,
                    "target_lon": coordinates.lon,
                    "target_alt": coordinates.alt,
                },
            )
        _validate_tolerance(tolerance, "tolerance")
        await self._require_can(self.can_goto(coordinates, tolerance=tolerance), "goto", NavigationError)
        if target_heading is not None:
            await self.set_heading(target_heading, blocking=False)
        await self.await_ready_to_move()
        await self._stop_velocity()
        gen = None
        try:
            # goto_location takes AMSL; never convert with an unknown home.
            self._require_movement_fix(NavigationError)
            heading = self._goto_yaw(coordinates)
            target_alt = coordinates.alt + self.home_amsl
            gen = self._begin_move()
            logger.debug(
                "Drone: goto_coordinates sending goto_location(%.6f, %.6f, alt=%.1f, hdg=%.1f)",
                coordinates.lat,
                coordinates.lon,
                target_alt,
                heading,
            )
            await self._system.action.goto_location(
                coordinates.lat,
                coordinates.lon,
                target_alt,
                heading,
            )
        except ActionError as e:
            logger.error(f"Drone: goto_location failed: {e}")
            self._release_move_gate(gen)  # reset so next command isn't blocked
            raise NavigationError(str(e), original_error=e) from e
        except BaseException:
            if gen is not None:
                self._release_move_gate(gen)
            raise
        finally:
            self._current_heading = None
        alt_tolerance = max(tolerance, _ARRIVAL_MIN_ALT_TOLERANCE_M)
        self._set_move_gate(
            gen,
            lambda s: coordinates.ground_distance(s.position) <= tolerance and abs(coordinates.alt - s.position.alt) <= alt_tolerance,
        )

        if blocking:
            from aerpawlib.cli.progress_bar import update_progress

            try:
                update_progress(state="Navigating")
                await wait_for_blocking_goto(
                    self,
                    coordinates,
                    distance_fn=lambda: coordinates.distance(self.position),
                    tolerance=tolerance,
                    timeout=timeout,
                    log_prefix="Drone",
                    generation=gen,
                )
                logger.debug("Drone: goto_coordinates complete (blocking)")
                if self._event_log:
                    self._event_log.log_event(
                        "location",
                        lat=self.position.lat,
                        lon=self.position.lon,
                        alt=self.position.alt,
                    )
                return None
            except BaseException:
                self._release_move_gate(gen)
                raise
            finally:
                update_progress(state="")

        def _log_location() -> None:
            if self._event_log:
                self._event_log.log_event(
                    "location",
                    lat=self.position.lat,
                    lon=self.position.lon,
                    alt=self.position.alt,
                )

        async def _on_cancel() -> None:
            # Stop now; do not wait for the original target (no LOITER/hold).
            if not self.closed and self._system is not None:
                await self._hold_current_position()
            else:
                logger.warning("Drone: _on_cancel skipped (vehicle closed)")

        return start_nonblocking_goto(
            self,
            coordinates,
            distance_fn=lambda: coordinates.distance(self.position),
            tolerance=tolerance,
            timeout=timeout,
            on_cancel=_on_cancel,
            log_prefix="Drone",
            on_complete=_log_location,
            generation=gen,
        )

    def _goto_yaw(self, coordinates: Coordinate) -> float:
        """Yaw for goto_location: locked heading, else bearing to target.

        A ~zero horizontal move (e.g. a pure climb) keeps the current heading
        instead of turning to the undefined bearing (0 = north).
        """
        if self._current_heading is not None:
            return self._current_heading
        pos = self.position
        if pos.ground_distance(coordinates) < _COINCIDENT_DISTANCE_M:
            return self.heading
        heading = pos.bearing(coordinates)
        if math.isnan(heading):
            return self.heading
        return heading

    async def _hold_current_position(self) -> None:
        """Stop in GUIDED by repositioning to the current fix.

        ``action.hold()`` is LOITER (mode 5), which the AERPAW filter rejects,
        so a DO_REPOSITION to where the drone is now is used everywhere.
        """
        gen = self._begin_move()
        pos = self.position
        try:
            self._require_movement_fix(NavigationError)
            logger.info("Drone: stopping at current position (%.6f, %.6f, alt=%.1fm)", pos.lat, pos.lon, pos.alt)
            await self._system.action.goto_location(
                pos.lat,
                pos.lon,
                self.home_amsl + pos.alt,
                self.heading,
            )
        finally:
            self._release_move_gate(gen)

    async def set_velocity(
        self,
        velocity: VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """Set the drone's velocity in the NED frame.

        Streams GUIDED velocity setpoints facing the locked heading (see
        :meth:`set_heading`), else the current heading. Returns at once; the
        velocity holds until ``duration`` expires, :meth:`stop_velocity` is
        called, or another movement command starts. Stopping hovers in place.
        The drone stays in GUIDED throughout, so this works on the AERPAW
        testbed, where the C-VM filter limits the speed and refuses a velocity
        that would leave the geofence within a few seconds.

        Args:
            velocity: Desired velocity as a NED vector (m/s); positive down
                descends.
            global_relative: If True (default), the vector is in the global NED
                frame. If False, the vector is rotated by the drone's current
                heading before being sent.
            duration: If given, hold the velocity for this many seconds then
                stop. If None, the velocity runs until the next command.

        Raises:
            VelocityError: If the velocity or duration is not finite, or the
                setpoint cannot be sent.
        """
        await self._start_velocity(velocity, global_relative, duration)

    def _velocity_setpoint(self, velocity: VectorNED) -> Any:
        from aerpawlib._internal.mavlink_ids import make_copter_velocity_message, resolve_mav_sysid

        yaw = self._current_heading if self._current_heading is not None else self.heading
        return make_copter_velocity_message(resolve_mav_sysid(self._system), velocity.north, velocity.east, velocity.down, yaw)

    def _velocity_stop_setpoint(self) -> Any:
        from aerpawlib._internal.mavlink_ids import make_copter_velocity_message, resolve_mav_sysid

        return make_copter_velocity_message(resolve_mav_sysid(self._system), 0.0, 0.0, 0.0, self.heading)

    async def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode.

        ArduPilot Drone/Copter requires GUIDED mode to accept takeoff/navigation commands.
        We send MAV_CMD_DO_SET_MODE directly using mavlink_direct,
        then poll/resend until the flight controller confirms the mode change.
        """
        if self._already_in_guided_mode():
            logger.debug(
                f"Drone: already in pre-arm mode {self.mode!r}, skipping mode switch",
            )
            return
        logger.info(
            f"Drone: switching to GUIDED (OFFBOARD) mode (current mode={self.mode!r})",
        )
        # action.hold() is LOITER (mode 5). The AERPAW E-VM filter only allows
        # GUIDED (4) and LAND (9) and severs the link on mode 5. Keep hold for
        # local SITL only. Skip hold whenever the OEO forwarder is reachable,
        # even if --no-aerpaw-environment left the platform unset.
        if not self._must_avoid_loiter():
            try:
                await self._system.action.hold()
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning(f"Drone: action.hold() failed: {e}")
            if self._already_in_guided_mode():
                logger.info(f"Drone: pre-arm mode confirmed ({self.mode})")
                return

        from aerpawlib._internal.mavlink_ids import make_set_mode_message, resolve_mav_sysid

        sysid = resolve_mav_sysid(self._system)
        msg = make_set_mode_message(sysid, COPTER_GUIDED_MODE)
        deadline = time.monotonic() + COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S
        last_send = 0.0
        while time.monotonic() < deadline:
            if self._already_in_guided_mode():
                logger.info(f"Drone: pre-arm mode confirmed ({self.mode})")
                return
            if time.monotonic() - last_send >= 0.5:
                try:
                    await self._system.mavlink_direct.send_message(msg)
                except Exception as e:
                    logger.warning(
                        f"Drone: failed to send GUIDED (OFFBOARD) mode command: {e}",
                    )
                last_send = time.monotonic()
            await asyncio.sleep(0.05)
        logger.warning(
            f"Drone: mode switch timeout (current mode={self.mode!r}); commands may fail if vehicle is not in GUIDED (OFFBOARD) mode",
        )
