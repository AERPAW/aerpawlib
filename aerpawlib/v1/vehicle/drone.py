"""MAVSDK-backed multirotor implementation for the v1 API.

See ``aerpawlib.v1.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import TYPE_CHECKING, Any

from mavsdk.action import ActionError

from aerpawlib.v1.constants import (
    ARMABLE_TIMEOUT_S,
    COPTER_GUIDED_MODE,
    COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S,
    DEFAULT_GOTO_TIMEOUT_S,
    DEFAULT_POSITION_TOLERANCE_M,
    DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    GPS_3D_FIX_TYPE,
    GUIDED_MODE_NAME,
    HEADING_TOLERANCE_DEG,
    MIN_ARM_TO_TAKEOFF_DELAY_S,
    POLLING_DELAY_S,
    POSITION_READY_TIMEOUT_S,
    POST_TAKEOFF_STABILIZATION_S,
    TELEMETRY_SUBSCRIPTION_TIMEOUT_S,
)
from aerpawlib.v1.exceptions import (
    HeadingError,
    LandingError,
    NavigationError,
    NotArmableError,
    RTLError,
    TakeoffError,
)
from aerpawlib.v1.helpers import (
    heading_difference,
    normalize_heading,
    validate_tolerance,
    wait_for_condition,
)
from aerpawlib.v1.log import LogComponent, get_logger
from aerpawlib.v1.vehicle.core_vehicle import Vehicle

if TYPE_CHECKING:
    from aerpawlib.v1 import util

logger = get_logger(LogComponent.DRONE)

# Horizontal moves shorter than this have no meaningful bearing.
_COINCIDENT_DISTANCE_M = 0.01
# Arrival checks altitude separately from the horizontal tolerance, with at
# least this much vertical slack.
_ARRIVAL_MIN_ALT_TOLERANCE_M = 3.0
# The C-VM filter aborts a land more than 5 m from the pad it recorded at
# takeoff. land() refuses before sending past this, leaving slack for the
# drone drifting while telemetry catches up.
_LAND_MAX_FROM_PAD_M = 4.5
# return_to_launch only lands in place after a failed home goto when this
# close to home.
_RTL_LAND_IN_PLACE_MAX_M = _LAND_MAX_FROM_PAD_M


def _is_valid_takeoff_altitude(altitude: float) -> bool:
    try:
        return math.isfinite(altitude) and altitude > 0
    except TypeError:
        return False


class Drone(Vehicle):
    """
    Drone implementation for multirotors.

    Provides core flight functionality including takeoff, landing,
    navigation, and velocity control.
    """

    def __init__(self, connection_string: str, mavsdk_server_port: int = 50051):
        """
        Initialize the drone and check for startup constraints.

        Args:
            connection_string: MAVLink connection string.
            mavsdk_server_port: Port for the embedded mavsdk_server gRPC interface.
                Each Vehicle instance should use a unique port to avoid conflicts.
                Defaults to 50051.

        Raises:
            NotArmableError: If the vehicle is already armed (safety check).
        """
        super().__init__(connection_string, mavsdk_server_port=mavsdk_server_port)
        # Ground position at the first takeoff since the last land; mirrors
        # the pad the C-VM filter pins landing to.
        self._takeoff_pad: util.Coordinate | None = None
        # Wait for armed-state telemetry to arrive before checking
        start = time.time()
        while not self._ts_state.armed_telemetry_received.get():
            if time.time() - start > TELEMETRY_SUBSCRIPTION_TIMEOUT_S:
                logger.warning(
                    "Timeout waiting for armed-state telemetry; proceeding anyway",
                )
                break
            time.sleep(POLLING_DELAY_S)
        if self.armed and not ("127.0.0.1" in connection_string or "localhost" in connection_string):
            # The caller gets no instance to close(): stop the MAVSDK thread
            # and mavsdk_server here.
            self._abort_connect()
            raise NotArmableError("Vehicle already armed at start!")

    async def set_heading(
        self,
        heading: float | None,
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """
        Command the drone to turn to a specific heading.

        Args:
            heading: Target heading in degrees (0-360).
                If None, clears any locked heading.
            blocking: Whether to wait for the drone to finish turning. A
                blocking turn ends a running set_velocity.
                Defaults to True.
            lock_in: If True, internal state will track this heading
                for future combined commands. Defaults to True.

        Raises:
            HeadingError: If the heading is not finite, the yaw command fails,
                or the turn does not finish in time. The previous heading lock
                is kept and the vehicle is marked ready for the next command.
        """
        if heading is not None and not math.isfinite(heading):
            raise HeadingError(f"heading must be finite (got {heading!r})")
        if blocking:
            await self.await_ready_to_move()

        if heading is None:
            logger.debug("Clearing locked heading")
            self._current_heading = None
            return

        heading = normalize_heading(heading)
        previous_lock = self._current_heading
        if lock_in:
            self._current_heading = heading
        if not blocking:
            # A running set_velocity keeps its yaw; the lock applies to the next one.
            return
        # The velocity stream would keep overriding the yaw: stop and turn.
        await self._stop_velocity()

        logger.debug(f"Turning to {heading} (current: {self.heading})")
        try:
            from aerpawlib._internal.mavlink_ids import (
                make_condition_yaw_message,
                resolve_mav_sysid,
            )

            sysid = resolve_mav_sysid(self._ts_state.autopilot_sysid.get())
            msg = make_condition_yaw_message(sysid, heading)
            await self._run_on_mavsdk_loop(
                self._system.mavlink_direct.send_message(msg),
            )
            self._ready_to_move = lambda s: heading_difference(heading, s.heading) <= HEADING_TOLERANCE_DEG
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message=f"turn to {heading} deg timed out after {DEFAULT_GOTO_TIMEOUT_S:.0f}s",
            )
        except Exception as e:
            logger.warning(f"set_heading error: {e}")
            self._ready_to_move = lambda _: True
            if lock_in:
                self._current_heading = previous_lock
            raise HeadingError(str(e), original_error=e) from e

    async def takeoff(
        self,
        target_alt: float,
        min_alt_tolerance: float = DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
        wait_for_throttle: bool = False,
    ) -> None:
        """
        Perform a takeoff to the target altitude.

        Args:
            target_alt: Target altitude Above Ground Level (meters).
            min_alt_tolerance: Fraction of target altitude to reach before
                continuing. Defaults to DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE.
            wait_for_throttle: Accepted for compatibility with the DroneKit
                aerpawlib signature. Ignored: the RC throttle check was
                removed (a warning is logged when True).

        Raises:
            TakeoffError: If the altitude is not a finite value > 0,
                ``min_alt_tolerance`` is not in (0, 1], or the takeoff command
                fails, times out, or is rejected by the autopilot.
        """
        if wait_for_throttle:
            logger.warning(
                "takeoff(wait_for_throttle=True) is ignored: the RC throttle check is not supported by this aerpawlib",
            )
        if not _is_valid_takeoff_altitude(target_alt):
            raise TakeoffError(f"Takeoff altitude must be a finite value > 0 m (got {target_alt!r})")
        was_armed = self.armed
        if not (isinstance(min_alt_tolerance, (int, float)) and 0 < min_alt_tolerance <= 1):
            raise TakeoffError(f"min_alt_tolerance must be in (0, 1] (got {min_alt_tolerance!r})")
        if not self.armed:
            try:
                await wait_for_condition(
                    lambda: self.armable,
                    timeout=ARMABLE_TIMEOUT_S,
                    poll_interval=POLLING_DELAY_S,
                    timeout_message=f"Vehicle not armable after {ARMABLE_TIMEOUT_S:.0f}s",
                )
                await wait_for_condition(
                    lambda: self.gps.fix_type >= GPS_3D_FIX_TYPE,
                    timeout=POSITION_READY_TIMEOUT_S,
                    poll_interval=POLLING_DELAY_S,
                    timeout_message=f"No GPS 3D fix after {POSITION_READY_TIMEOUT_S:.0f}s",
                )
            except TimeoutError as e:
                raise TakeoffError(str(e)) from e
        if self.safety is not None:
            ok, msg = self.safety.validate_takeoff_command(
                target_alt,
                self.position.lat,
                self.position.lon,
            )
            if not ok:
                raise TakeoffError(f"takeoff rejected by safety checks: {msg}")
        await self.await_ready_to_move()
        await self._stop_velocity()

        # Enforce minimum delay between arming and takeoff
        time_since_arm = time.time() - self._ts_state.last_arm_time.get()
        if time_since_arm < MIN_ARM_TO_TAKEOFF_DELAY_S:
            delay = MIN_ARM_TO_TAKEOFF_DELAY_S - time_since_arm
            logger.debug(
                f"Delaying takeoff by {delay:.2f}s to satisfy minimum arm-to-takeoff time",
            )
            await asyncio.sleep(delay)

        if self._mission_start_time is None:
            self._mission_start_time = time.time()

        from aerpawlib.cli.progress_bar import update_progress

        ok = False
        try:
            update_progress(state="Taking off")
            logger.debug(f"Takeoff to {target_alt}m")
            await self._run_on_mavsdk_loop(
                self._system.action.set_takeoff_altitude(target_alt),
            )
            ground = self.position
            await self._run_on_mavsdk_loop(self._system.action.takeoff())
            # The filter keeps its pad until disarm, so a takeoff while
            # already airborne does not move it.
            if self._takeoff_pad is None or not was_armed:
                self._takeoff_pad = ground

            # Non-finite altitude samples never count as reached.
            self._ready_to_move = lambda s: math.isfinite(s.position.alt) and s.position.alt >= target_alt * min_alt_tolerance
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message=f"Takeoff timed out after {DEFAULT_GOTO_TIMEOUT_S:.0f}s",
            )
            await asyncio.sleep(POST_TAKEOFF_STABILIZATION_S)
            ok = True
        except TimeoutError as e:
            logger.error(f"Takeoff failed: {e}")
            raise TakeoffError(str(e), original_error=e) from e
        except ActionError as e:
            logger.error(f"Takeoff failed: {e}")
            err_msg = f"Takeoff failed: {e}"
            if self.armed:
                err_msg += " (drone is already armed)"
            raise TakeoffError(err_msg, original_error=e) from e
        finally:
            if not ok:
                self._ready_to_move = lambda _: True
            update_progress(state="")

    async def _action_wait_disarm(self, coro, name, exc_cls):
        """
        Internal helper to execute an action and wait for the drone to disarm.

        Args:
            coro: The MAVSDK coroutine to run.
            name: Label for logging.
            exc_cls: Exception class to raise on failure.

        Does not wait for a previous goto/takeoff/turn to finish: landing
        preempts it. The vehicle stays busy until it disarms.
        """
        if not self.armed:
            await self._arm_vehicle()
        if self.safety is not None and name == "land":
            ok, msg = self.safety.validate_landing_command(
                self.position.lat,
                self.position.lon,
            )
            if not ok:
                raise exc_cls(f"land rejected by safety checks: {msg}")
        self._abortable = False
        await self._stop_velocity()
        from aerpawlib.cli.progress_bar import update_progress

        self._ready_to_move = lambda _: False
        try:
            update_progress(state="Landing")
            logger.debug(f"Executing {name}, waiting for disarm...")
            await self._run_on_mavsdk_loop(coro)
            await wait_for_condition(
                lambda: not self.armed,
                poll_interval=POLLING_DELAY_S,
                timeout=DEFAULT_GOTO_TIMEOUT_S,
                timeout_message=f"{name} timed out waiting for disarm",
            )
            logger.debug(f"{name} complete")
        except (ActionError, TimeoutError) as e:
            logger.error(f"{name} failed: {e}")
            raise exc_cls(str(e), original_error=e) from e
        finally:
            self._ready_to_move = lambda _: True
            update_progress(state="")

    async def land(self) -> None:
        """Land the drone and wait for it to be disarmed.

        Raises:
            LandingError: If the drone is more than 4.5 m from where it took
                off (the C-VM filter would abort the land), or the land fails.
        """
        self._check_not_taken_over("land")
        if self._takeoff_pad is not None:
            away = self.position.ground_distance(self._takeoff_pad)
            if not away <= _LAND_MAX_FROM_PAD_M:
                raise LandingError(
                    f"{away:.1f} m from the takeoff pad (limit {_LAND_MAX_FROM_PAD_M} m); fly back to the pad before landing",
                )
        self._takeover.note_land()
        await self._action_wait_disarm(self._system.action.land(), "land", LandingError)
        self._takeoff_pad = None

    async def return_to_launch(self) -> None:
        """Fly to home coordinates and land (RTL mode is not used)."""
        home = self.home_coords
        if home is None:
            logger.error("Return-to-launch requested but home coordinates are unset")
            raise RTLError("Home coordinates are not available for return-to-launch")
        from aerpawlib.cli.progress_bar import update_progress

        dest = type(home)(home.lat, home.lon, self.position.alt)
        try:
            update_progress(state="Returning home")
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
            logger.error(f"Return-to-launch failed: {e}")
            raise RTLError(str(e), original_error=e) from e
        finally:
            update_progress(state="")

    async def goto_coordinates(
        self,
        coordinates: util.Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
    ) -> None:
        """
        Make the vehicle go to provided coordinates.

        Args:
            coordinates: Target position
            tolerance: Distance in meters to consider destination reached
            target_heading: Optional heading to maintain during movement
            timeout: Maximum time to wait for completion in seconds (C3)

        Raises:
            ValueError: If tolerance is out of acceptable range
            NavigationError: If navigation command fails
        """
        validate_tolerance(tolerance, "tolerance")
        if self.safety is not None:
            ok, msg = self.safety.validate_waypoint_command(self.position, coordinates)
            if not ok:
                raise NavigationError(f"goto rejected by safety checks: {msg}")
        if target_heading is not None:
            await self.set_heading(target_heading, blocking=False)

        await self.await_ready_to_move()
        await self._stop()

        from aerpawlib.cli.progress_bar import update_progress

        try:
            # goto_location takes AMSL; never convert with an unknown home.
            self._require_movement_fix(NavigationError)
            self._ready_to_move = lambda _: False
            heading = self._goto_yaw(coordinates)
            update_progress(state="Navigating")
            target_alt = coordinates.alt + self.home_amsl
            logger.debug(
                f"Goto: {coordinates.lat}, {coordinates.lon}, alt={target_alt}, heading={heading}",
            )
            await self._run_on_mavsdk_loop(
                self._system.action.goto_location(
                    coordinates.lat,
                    coordinates.lon,
                    target_alt,
                    heading,
                ),
            )

            alt_tolerance = max(tolerance, _ARRIVAL_MIN_ALT_TOLERANCE_M)
            self._ready_to_move = lambda s: coordinates.ground_distance(s.position) <= tolerance and abs(coordinates.alt - s.position.alt) <= alt_tolerance
            await self._wait_for_arrival(
                timeout,
                f"Drone failed to reach destination {coordinates} within {timeout}s",
            )
            logger.debug("Arrived at destination")
        except ActionError as e:
            logger.error(f"Goto failed: {e}")
            self._ready_to_move = lambda _: True
            raise NavigationError(str(e), original_error=e) from e
        except TimeoutError as e:
            logger.error(f"Goto timed out: {e}")
            self._ready_to_move = lambda _: True
            raise NavigationError(str(e), original_error=e) from e
        except BaseException:
            self._ready_to_move = lambda _: True
            raise
        finally:
            # Clear locked heading so it does not contaminate subsequent commands
            self._current_heading = None
            update_progress(state="")

    def _goto_yaw(self, coordinates: util.Coordinate) -> float:
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

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """
        Set the drone's velocity in NED frame.

        Streams GUIDED velocity setpoints facing the locked heading (see
        `set_heading`), else the current heading. Returns at once; the velocity
        holds until `duration` expires or the next movement command. Stopping
        hovers in place. The drone stays in GUIDED throughout, so this works on
        the AERPAW testbed, where the C-VM filter limits the speed and refuses
        a velocity that would leave the geofence within a few seconds.

        Args:
            velocity_vector: Target velocity; positive down descends.
            global_relative: If True, north/east are world-aligned.
                If False, they are relative to current heading. Defaults to True.
            duration: How long to maintain this velocity.
                If None, maintains it until stopped or changed.

        Raises:
            VelocityError: If the velocity or duration is not finite, or the
                setpoint cannot be sent.
        """
        await self._start_velocity(velocity_vector, global_relative, duration)

    def _velocity_setpoint(self, velocity_vector: util.VectorNED) -> Any:
        from aerpawlib._internal.mavlink_ids import make_copter_velocity_message, resolve_mav_sysid

        yaw = self._current_heading if self._current_heading is not None else self.heading
        return make_copter_velocity_message(
            resolve_mav_sysid(self._ts_state.autopilot_sysid.get()),
            velocity_vector.north,
            velocity_vector.east,
            velocity_vector.down,
            yaw,
        )

    def _velocity_stop_setpoint(self) -> Any:
        from aerpawlib._internal.mavlink_ids import make_copter_velocity_message, resolve_mav_sysid

        return make_copter_velocity_message(resolve_mav_sysid(self._ts_state.autopilot_sysid.get()), 0.0, 0.0, 0.0, self.heading)

    async def _set_guided_mode(self) -> None:
        """Switch to GUIDED mode.

        ArduPilot Drone/Copter requires GUIDED mode to accept takeoff/navigation commands.
        We send MAV_CMD_DO_SET_MODE directly using mavlink_direct,
        then poll/resend until the flight controller confirms the mode change.
        """
        if self._already_in_guided_mode():
            logger.debug(
                f"Drone: already in pre-arm mode {self._ts_state.mode.get()!r}, skipping mode switch",
            )
            return
        logger.info(
            f"Drone: switching to GUIDED ({GUIDED_MODE_NAME}) mode (current mode={self._ts_state.mode.get()!r})",
        )
        # action.hold() is LOITER (mode 5). The AERPAW E-VM filter only allows
        # GUIDED (4) and LAND (9) and severs the link on mode 5. Keep hold for
        # local SITL only. On AERPAW, HOLD is not already GUIDED. AERPAW env
        # vars also count, so --no-aerpaw-environment cannot send LOITER.
        if not self._must_avoid_loiter():
            try:
                await self._run_on_mavsdk_loop(self._system.action.hold())
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning(f"Drone: action.hold() failed: {e}")
        if self._already_in_guided_mode():
            logger.info(
                f"Drone: pre-arm mode confirmed ({self._ts_state.mode.get()})",
            )
            return

        from aerpawlib._internal.mavlink_ids import make_set_mode_message, resolve_mav_sysid

        sysid = resolve_mav_sysid(self._ts_state.autopilot_sysid.get())
        msg = make_set_mode_message(sysid, COPTER_GUIDED_MODE)

        start = time.time()
        last_send = 0.0
        while not self._already_in_guided_mode():
            if time.time() - start > COPTER_GUIDED_MODE_SWITCH_TIMEOUT_S:
                logger.warning(
                    f"Drone: mode switch timeout (current mode={self._ts_state.mode.get()!r}); commands may fail if vehicle is not in GUIDED ({GUIDED_MODE_NAME}) mode",
                )
                return
            if time.time() - last_send >= 0.5:
                try:
                    await self._run_on_mavsdk_loop(
                        self._system.mavlink_direct.send_message(msg),
                    )
                except Exception as e:
                    logger.warning(
                        f"Drone: failed to send GUIDED ({GUIDED_MODE_NAME}) mode command: {e}",
                    )
                last_send = time.time()
            await asyncio.sleep(POLLING_DELAY_S)
        logger.info(f"Drone: GUIDED ({GUIDED_MODE_NAME}) mode confirmed")
