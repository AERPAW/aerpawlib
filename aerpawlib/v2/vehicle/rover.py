"""MAVSDK-backed ground vehicle implementation for the v2 API.

See ``aerpawlib.v2.vehicle`` module documentation for usage and commands.
"""

from __future__ import annotations

import math
from typing import Any

from mavsdk.action import ActionError

from aerpawlib.v2.constants import (
    DEFAULT_GOTO_TIMEOUT_S,
    GOTO_POLL_INTERVAL_S,
    ROVER_GUIDED_MODE,
    ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
)
from aerpawlib.v2.exceptions import NavigationError
from aerpawlib.v2.log import LogComponent, get_logger
from aerpawlib.v2.types import Coordinate, VectorNED

from .base import Vehicle, _wait_for_condition
from .connection_helpers import _validate_tolerance
from .navigation import start_nonblocking_goto, wait_for_blocking_goto
from .task import VehicleTask

logger = get_logger(LogComponent.ROVER)

# Ground rover navigation uses horizontal distance only for arrival checks.
DEFAULT_ROVER_POSITION_TOLERANCE_M = 2.1
# Below this a velocity has no direction: ArduRover would steer north
# (atan2(0, 0)), so the rover holds its heading at speed 0 instead.
_STOPPED_SPEED_M_S = 1e-3


class Rover(Vehicle):
    """Rover implementation for ground vehicles."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise rover movement state."""
        super().__init__(*args, **kwargs)

    @property
    def _default_goto_tolerance(self) -> float:
        return DEFAULT_ROVER_POSITION_TOLERANCE_M

    def _vehicle_type_label(self) -> str:
        return "rover"

    async def _preflight_wait(self, should_arm: bool = True) -> None:
        """Switch to GUIDED mode, then wait for armable state."""
        self._will_arm = should_arm
        if not self._in_aerpaw():
            await self._set_guided_mode()
        await self._wait_for_armable(log_prefix="Rover: ")

    async def _pre_auto_arm(self) -> None:
        await self._set_guided_mode()

    async def _set_guided_mode(self) -> None:
        """Switch the rover to GUIDED mode before arming.

        ArduPilot Rover requires GUIDED mode to accept arm commands via
        MAVLink. MAVSDK does not expose a direct flight-mode setter for
        ArduPilot due to incompatibility with its custom mode system, so
        this method sends a raw ``MAV_CMD_DO_SET_MODE`` command through
        ``mavlink_direct`` and waits for the mode telemetry to update.
        """
        if self.mode == "OFFBOARD":
            logger.debug(
                "Rover: already in GUIDED (OFFBOARD) mode, skipping mode switch",
            )
            return
        await self._require_may_command("switch to GUIDED")
        logger.info(
            f"Rover: switching to GUIDED (OFFBOARD) mode (current mode={self.mode!r})",
        )
        try:
            from aerpawlib._internal.mavlink_ids import make_set_mode_message, resolve_mav_sysid

            sysid = resolve_mav_sysid(self._state.autopilot_sysid)
            msg = make_set_mode_message(sysid, ROVER_GUIDED_MODE)
            await self._system.mavlink_direct.send_message(msg)
        except Exception as e:
            logger.warning(f"Rover: failed to send GUIDED (OFFBOARD) mode command: {e}")
            return

        try:
            await _wait_for_condition(
                lambda: self.mode == "OFFBOARD",
                timeout=ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S,
                timeout_message=(f"Rover did not enter GUIDED (OFFBOARD) mode within {ROVER_GUIDED_MODE_SWITCH_TIMEOUT_S}s"),
            )
            logger.info("Rover: GUIDED (OFFBOARD) mode confirmed")
        except TimeoutError:
            logger.warning(
                f"Rover: mode switch timeout (current mode={self.mode!r}); arming may fail if vehicle is not in GUIDED (OFFBOARD) mode",
            )

    async def goto_coordinates(
        self,
        coordinates: Coordinate,
        tolerance: float = DEFAULT_ROVER_POSITION_TOLERANCE_M,
        target_heading: float | None = None,
        timeout: float = DEFAULT_GOTO_TIMEOUT_S,
        blocking: bool = True,
    ) -> VehicleTask | None:
        """Navigate to a target coordinate using ground-distance arrival.

        Args:
            coordinates: Target position.
            tolerance: Arrival tolerance in metres (ground distance).
            target_heading: Unused for rovers; accepted for API parity.
            timeout: Maximum seconds to wait for arrival.
            blocking: If False, returns a VehicleTask immediately.

        Returns:
            None when blocking=True; VehicleTask when blocking=False.

        Raises:
            NavigationError: If the target is not finite, there is no position
                fix or known home AMSL yet, command dispatch fails, or arrival
                times out / the link drops.
        """
        _validate_tolerance(tolerance, "tolerance")
        await self._require_can(self.can_goto(coordinates, tolerance=tolerance), "goto", NavigationError)
        await self.await_ready_to_move()
        await self._stop_velocity()
        # goto_location takes AMSL; rovers send the home AMSL altitude.
        self._require_movement_fix(NavigationError)
        gen = self._begin_move()
        logger.debug(
            "Rover: sending goto_location(%.6f, %.6f) command",
            coordinates.lat,
            coordinates.lon,
        )
        try:
            await self._system.action.goto_location(
                coordinates.lat,
                coordinates.lon,
                self.home_amsl,
                0,
            )
        except ActionError as e:
            logger.error(f"Rover: goto_coordinates failed (ActionError): {e}")
            self._release_move_gate(gen)
            raise NavigationError(str(e), original_error=e) from e
        except BaseException:
            self._release_move_gate(gen)
            raise

        self._set_move_gate(gen, lambda s: coordinates.ground_distance(s.position) <= tolerance)

        if blocking:
            from aerpawlib.cli.progress_bar import update_progress

            try:
                update_progress(state="Navigating")
                await wait_for_blocking_goto(
                    self,
                    coordinates,
                    distance_fn=lambda: coordinates.ground_distance(self.position),
                    tolerance=tolerance,
                    timeout=timeout,
                    log_prefix="Rover",
                    generation=gen,
                )
                return None
            except NavigationError as e:
                logger.error(f"Rover: goto_coordinates failed: {e}")
                self._release_move_gate(gen)
                raise
            except BaseException:
                self._release_move_gate(gen)
                raise
            finally:
                update_progress(state="")

        async def _on_cancel() -> None:
            if self.closed or self._system is None:
                logger.warning("Rover: _on_cancel skipped (vehicle closed)")
                return
            cancel_gen = self._begin_move()
            try:
                if self._must_avoid_loiter():
                    # hold() is LOITER/HOLD, fatal on AERPAW: stop in GUIDED by
                    # repositioning to the current fix instead.
                    await self._require_may_command("stop")
                    pos = self.position
                    self._require_movement_fix(NavigationError)
                    await self._system.action.goto_location(pos.lat, pos.lon, self.home_amsl, 0)
                else:
                    await self._system.action.hold()
            except Exception as exc:
                logger.warning(f"Rover: _on_cancel stop failed: {exc}")
            finally:
                self._release_move_gate(cancel_gen)

        return start_nonblocking_goto(
            self,
            coordinates,
            distance_fn=lambda: coordinates.ground_distance(self.position),
            tolerance=tolerance,
            timeout=timeout,
            on_cancel=_on_cancel,
            log_prefix="Rover",
            progress_poll_interval=GOTO_POLL_INTERVAL_S,
            generation=gen,
        )

    async def set_velocity(
        self,
        velocity_vector: VectorNED,
        global_relative: bool = True,
        duration: float | None = None,
    ) -> None:
        """Set rover velocity in GUIDED mode.

        Streams GUIDED velocity setpoints; ArduRover steers toward the vector's
        direction. The vertical component is ignored since rovers are ground
        vehicles. Returns at once; the velocity holds until ``duration``
        expires, :meth:`stop_velocity` is called, or another movement command
        starts. Stopping (or a zero vector) holds the current heading at speed
        0, so the rover never leaves GUIDED and this works on the AERPAW
        testbed, where the C-VM filter limits the speed and refuses a velocity
        that would leave the geofence within a few seconds.

        Args:
            velocity_vector: Desired velocity as a NED vector (m/s). Down
                component is ignored.
            global_relative: If True (default), the vector is in the global NED
                frame. If False, the vector is rotated by the rover's heading
                before being sent.
            duration: Hold velocity for this many seconds then stop. If None,
                the velocity loop runs until the next movement command.

        Raises:
            VelocityError: If the velocity or duration is not finite, or the
                setpoint cannot be sent.
        """
        await self._start_velocity(velocity_vector, global_relative, duration)

    def _velocity_setpoint(self, velocity: VectorNED) -> Any:
        from aerpawlib._internal.mavlink_ids import make_rover_velocity_message, resolve_mav_sysid

        if math.hypot(velocity.north, velocity.east) < _STOPPED_SPEED_M_S:
            return self._velocity_stop_setpoint()
        return make_rover_velocity_message(resolve_mav_sysid(self._state.autopilot_sysid), velocity.north, velocity.east)

    def _velocity_stop_setpoint(self) -> Any:
        from aerpawlib._internal.mavlink_ids import make_rover_stop_message, resolve_mav_sysid

        return make_rover_stop_message(resolve_mav_sysid(self._state.autopilot_sysid), self.heading)
