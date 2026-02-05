"""
Drone vehicle implementation.
"""

import asyncio
import logging
import math
import time
from typing import Optional

from mavsdk.offboard import PositionNedYaw, VelocityNedYaw, OffboardError
from mavsdk.action import ActionError

from aerpawlib.v1 import util
from aerpawlib.v1.constants import (
    POLLING_DELAY_S,
    DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    POST_TAKEOFF_STABILIZATION_S,
    HEADING_TOLERANCE_DEG,
    VELOCITY_UPDATE_DELAY_S,
    DEFAULT_POSITION_TOLERANCE_M,
    MIN_ARM_TO_TAKEOFF_DELAY_S,
)
from aerpawlib.v1.exceptions import (
    TakeoffError,
    LandingError,
    RTLError,
    NavigationError,
    VelocityError,
    NotArmableError,
)
from aerpawlib.v1.helpers import (
    wait_for_condition,
    validate_tolerance,
    validate_altitude,
    normalize_heading,
    heading_difference,
)
from aerpawlib.v1.vehicles.core_vehicle import Vehicle

logger = logging.getLogger(__name__)


class Drone(Vehicle):
    """
    Drone implementation for multirotors.

    Provides core flight functionality including takeoff, landing,
    navigation, and velocity control.

    Attributes:
        _velocity_loop_active (bool): Whether a background velocity command loop is running.
    """

    _velocity_loop_active: bool = False

    def __init__(self, connection_string: str):
        """
        Initialize the drone and check for startup constraints.

        Args:
            connection_string (str): MAVLink connection string.

        Raises:
            NotArmableError: If the vehicle is already armed (safety check).
        """
        super().__init__(connection_string)
        # Give telemetry a moment to populate (including armed state)
        time.sleep(1.0)  # TODO: remove this sleep with better async init
        if self.armed:
            raise NotArmableError("Vehicle already armed at start!")

    async def set_heading(
        self,
        heading: Optional[float],
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """
        Command the drone to turn to a specific heading.

        Args:
            heading (float, optional): Target heading in degrees (0-360).
                If None, clears any locked heading.
            blocking (bool, optional): Whether to wait for the drone to finish turning.
                Defaults to True.
            lock_in (bool, optional): If True, internal state will track this heading
                for future combined commands. Defaults to True.
        """
        if blocking:
            await self.await_ready_to_move()

        if heading is None:
            logger.debug("Clearing locked heading")
            self._current_heading = None
            return

        heading = normalize_heading(heading)
        if lock_in:
            self._current_heading = heading
        if not blocking:
            return

        logger.debug(f"Turning to {heading} (current: {self.heading})")
        try:
            await self._run_on_mavsdk_loop(
                self._system.offboard.set_position_ned(
                    PositionNedYaw(0, 0, -self._position_alt.get(), heading)
                )
            )
            try:
                await self._run_on_mavsdk_loop(self._system.offboard.start())
            except OffboardError:
                pass

            self._ready_to_move = (
                lambda s: heading_difference(heading, s.heading)
                <= HEADING_TOLERANCE_DEG
            )
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
            )
            await self._run_on_mavsdk_loop(self._system.offboard.stop())
        except (OffboardError, ActionError):
            pass

    async def takeoff(
        self,
        target_alt: float,
        min_alt_tolerance: float = DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    ) -> None:
        """
        Perform a takeoff to the target altitude.

        Args:
            target_alt (float): Target altitude Above Ground Level (meters).
            min_alt_tolerance (float, optional): Fraction of target altitude
                to reach before continuing. Defaults to DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE.

        Raises:
            TakeoffError: If the takeoff command fails or is rejected by the autopilot.
        """
        validate_altitude(target_alt, "target_alt")
        await self.await_ready_to_move()

        # Enforce minimum delay between arming and takeoff
        time_since_arm = time.time() - self._last_arm_time.get()
        if time_since_arm < MIN_ARM_TO_TAKEOFF_DELAY_S:
            delay = MIN_ARM_TO_TAKEOFF_DELAY_S - time_since_arm
            logger.debug(f"Delaying takeoff by {delay:.2f}s to satisfy minimum arm-to-takeoff time")
            await asyncio.sleep(delay)

        if self._mission_start_time is None:
            self._mission_start_time = time.time()

        try:
            logger.debug(f"Takeoff to {target_alt}m")
            await self._run_on_mavsdk_loop(
                self._system.action.set_takeoff_altitude(target_alt)
            )
            await self._run_on_mavsdk_loop(self._system.action.takeoff())

            self._ready_to_move = (
                lambda s: s.position.alt >= target_alt * min_alt_tolerance
            )
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
            )
            await asyncio.sleep(POST_TAKEOFF_STABILIZATION_S)
        except ActionError as e:
            logger.error(f"Takeoff failed: {e}")
            raise TakeoffError(str(e), original_error=e)

    async def _action_wait_disarm(self, coro, name, exc_cls):
        """
        Internal helper to execute an action and wait for the drone to disarm.

        Args:
            coro: The MAVSDK coroutine to run.
            name (str): Label for logging.
            exc_cls (Type[Exception]): Exception class to raise on failure.
        """
        await self.await_ready_to_move()
        self._abortable = False
        try:
            logger.debug(f"Executing {name}, waiting for disarm...")
            await self._run_on_mavsdk_loop(coro)
            self._ready_to_move = lambda _: False
            await wait_for_condition(
                lambda: not self.armed, poll_interval=POLLING_DELAY_S
            )
            logger.debug(f"{name} complete")
        except ActionError as e:
            logger.error(f"{name} failed: {e}")
            raise exc_cls(str(e), original_error=e)

    async def land(self) -> None:
        """Land the drone and wait for it to be disarmed."""
        await self._action_wait_disarm(
            self._system.action.land(), "land", LandingError
        )

    async def return_to_launch(self) -> None:
        """Command the drone to RTL and wait for it to land and disarm."""
        await self._action_wait_disarm(
            self._system.action.return_to_launch(), "RTL", RTLError
        )

    async def goto_coordinates(
        self,
        coordinates: util.Coordinate,
        tolerance: float = DEFAULT_POSITION_TOLERANCE_M,
        target_heading: Optional[float] = None,
    ) -> None:
        """
        Make the vehicle go to provided coordinates.

        Args:
            coordinates: Target position
            tolerance: Distance in meters to consider destination reached
            target_heading: Optional heading to maintain during movement

        Raises:
            ValueError: If tolerance is out of acceptable range
            NavigationError: If navigation command fails
        """
        validate_tolerance(tolerance, "tolerance")
        if target_heading is not None:
            await self.set_heading(target_heading, blocking=False)

        await self.await_ready_to_move()
        await self._stop()

        self._ready_to_move = lambda _: False
        heading = (
            self._current_heading
            if self._current_heading is not None
            else self.position.bearing(coordinates)
        )

        try:
            target_alt = coordinates.alt + self.home_amsl
            logger.debug(
                f"Goto: {coordinates.lat}, {coordinates.lon}, alt={target_alt}, heading={heading}"
            )
            await self._run_on_mavsdk_loop(
                self._system.action.goto_location(
                    coordinates.lat,
                    coordinates.lon,
                    target_alt,
                    heading if not math.isnan(heading) else 0,
                )
            )

            self._ready_to_move = (
                lambda s: coordinates.distance(s.position) <= tolerance
            )
            await wait_for_condition(
                lambda: self._ready_to_move(self),
                poll_interval=POLLING_DELAY_S,
                timeout=300,
                timeout_message=f"Failed to reach target within 300s",
            )
            logger.debug(f"Arrived at destination")
        except ActionError as e:
            logger.error(f"Goto failed: {e}")
            raise NavigationError(str(e), original_error=e)

    async def set_velocity(
        self,
        velocity_vector: util.VectorNED,
        global_relative: bool = True,
        duration: Optional[float] = None,
    ) -> None:
        """
        Set the drone's velocity in NED frame.

        Args:
            velocity_vector (VectorNED): Target velocity.
            global_relative (bool, optional): If True, north/east are world-aligned.
                If False, they are relative to current heading. Defaults to True.
            duration (float, optional): How long to maintain this velocity.
                If None, maintains it until stopped or changed.

        Raises:
            VelocityError: If offboard mode cannot be started.
        """
        await self.await_ready_to_move()
        self._velocity_loop_active = False
        await asyncio.sleep(POLLING_DELAY_S)

        if not global_relative:
            velocity_vector = velocity_vector.rotate_by_angle(-self.heading)

        yaw = (
            self._current_heading
            if self._current_heading is not None
            else self.heading
        )
        logger.debug(f"Set velocity: {velocity_vector}, yaw={yaw}")

        try:
            await self._run_on_mavsdk_loop(
                self._system.offboard.set_velocity_ned(
                    VelocityNedYaw(
                        velocity_vector.north,
                        velocity_vector.east,
                        velocity_vector.down,
                        yaw,
                    )
                )
            )
            try:
                await self._run_on_mavsdk_loop(self._system.offboard.start())
            except OffboardError:
                pass

            self._ready_to_move = lambda _: True
            target_end = (
                time.time() + duration if duration is not None else None
            )

            async def _velocity_helper():
                while self._velocity_loop_active:
                    if target_end and time.time() > target_end:
                        self._velocity_loop_active = False
                        await self._run_on_mavsdk_loop(
                            self._system.offboard.stop()
                        )
                    await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)

            self._velocity_loop_active = True
            asyncio.ensure_future(_velocity_helper())
        except (OffboardError, ActionError) as e:
            raise VelocityError(str(e), original_error=e)

    async def _stop(self) -> None:
        await super()._stop()
        self._velocity_loop_active = False
