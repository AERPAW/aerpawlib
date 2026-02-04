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
    Drone vehicle type. Implements all functionality that AERPAW's drones
    expose to user scripts, which includes basic movement control (going to
    coords, turning, landing).
    """

    _velocity_loop_active: bool = False

    def __init__(self, connection_string: str):
        super().__init__(connection_string)
        # Give telemetry a moment to populate (including armed state)
        time.sleep(1.0)
        if self.armed:
            raise NotArmableError("Vehicle already armed at start!")

    async def set_heading(
        self,
        heading: Optional[float],
        blocking: bool = True,
        lock_in: bool = True,
    ) -> None:
        """
        Set the heading of the vehicle (in absolute deg).

        To turn a relative # of degrees, you can do something like
        `drone.set_heading(drone.heading + x)`

        Pass in `None` to make the drone return to ardupilot's default heading
        behavior (usually facing the direction of movement)

        Args:
            heading: Target heading in degrees (0-360), or None to clear locked heading
            blocking: If True, wait for heading to be reached
            lock_in: If True, maintain this heading during subsequent movements
        """
        logger.debug(
            f"set_heading(heading={heading}, blocking={blocking}, lock_in={lock_in}) called"
        )
        if blocking:
            await self.await_ready_to_move()

        if heading is None:
            logger.debug(
                "Clearing locked heading, returning to default behavior"
            )
            self._current_heading = None
            return

        heading = normalize_heading(heading)
        if lock_in:
            self._current_heading = heading
        if not blocking:
            return

        logger.debug(f"Turning to heading {heading}° (current: {self.heading}°)")
        try:
            await self._run_on_mavsdk_loop(self._system.offboard.set_position_ned(
                    PositionNedYaw(0, 0, -self._position_alt.get(), heading)))
            try:
                logger.debug("Starting offboard mode for heading control")
                await self._run_on_mavsdk_loop(self._system.offboard.start())
            except OffboardError: pass

            self._ready_to_move = lambda s: heading_difference(heading, s.heading) <= HEADING_TOLERANCE_DEG
            await wait_for_condition(lambda: self._ready_to_move(self), poll_interval=POLLING_DELAY_S)

            logger.debug("Stopping offboard mode")
            await self._run_on_mavsdk_loop(self._system.offboard.stop())
        except (OffboardError, ActionError): pass

    async def takeoff(
        self,
        target_alt: float,
        min_alt_tolerance: float = DEFAULT_TAKEOFF_ALTITUDE_TOLERANCE,
    ) -> None:
        """
        Make the drone take off to a specific altitude, and blocks until the
        drone has reached that altitude.

        Args:
            target_alt: Target altitude in meters AGL
            min_alt_tolerance: Fraction of target altitude to consider takeoff complete (0.0-1.0)

        Raises:
            ValueError: If target_alt is out of acceptable range
            TakeoffError: If takeoff command fails
        """
        validate_altitude(target_alt, "target_alt")
        logger.debug(f"takeoff(target_alt={target_alt}, min_alt_tolerance={min_alt_tolerance}) called")
        await self.await_ready_to_move()

        if self._mission_start_time is None:
            self._mission_start_time = time.time()

        try:
            logger.debug(f"Setting takeoff altitude to {target_alt}m")
            await self._run_on_mavsdk_loop(self._system.action.set_takeoff_altitude(target_alt))
            logger.debug("Sending takeoff command...")
            await self._run_on_mavsdk_loop(self._system.action.takeoff())

            self._ready_to_move = lambda s: s.position.alt >= target_alt * min_alt_tolerance
            logger.debug(f"Waiting to reach altitude {target_alt * min_alt_tolerance}m...")
            await wait_for_condition(lambda: self._ready_to_move(self), poll_interval=POLLING_DELAY_S)

            logger.debug(f"Reached target altitude, current alt: {self.position.alt}m")
            await asyncio.sleep(POST_TAKEOFF_STABILIZATION_S)
        except ActionError as e:
            logger.error(f"Takeoff failed: {e}")
            raise TakeoffError(str(e), original_error=e)

    async def _action_wait_disarm(self, coro, name, exc_cls):
        await self.await_ready_to_move()
        self._abortable = False
        try:
            logger.debug(f"Sending {name} command..."); await self._run_on_mavsdk_loop(coro)
            self._ready_to_move = lambda _: False
            logger.debug(f"Waiting for {name} to complete and disarm...")
            await wait_for_condition(lambda: not self.armed, poll_interval=POLLING_DELAY_S)
            logger.debug(f"{name} complete")
        except ActionError as e:
            logger.error(f"{name} failed: {e}"); raise exc_cls(str(e), original_error=e)

    async def land(self) -> None:
        """Land the drone and wait for it to be disarmed."""
        await self._action_wait_disarm(self._system.action.land(), "land", LandingError)

    async def return_to_launch(self) -> None:
        """Command the drone to RTL and wait for it to land and disarm."""
        await self._action_wait_disarm(self._system.action.return_to_launch(), "RTL", RTLError)

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
        logger.debug(f"goto_coordinates({coordinates.lat}, {coordinates.lon}, {coordinates.alt}, tolerance={tolerance})")
        if target_heading is not None: await self.set_heading(target_heading, blocking=False)

        await self.await_ready_to_move()
        await self._stop()

        self._ready_to_move = lambda _: False
        heading = self._current_heading if self._current_heading is not None else self.position.bearing(coordinates)

        try:
            target_alt = coordinates.alt + self.home_amsl
            logger.debug(f"Navigating to: {coordinates.lat}, {coordinates.lon}, alt={target_alt}, heading={heading}")
            await self._run_on_mavsdk_loop(self._system.action.goto_location(
                    coordinates.lat, coordinates.lon, target_alt, heading if not math.isnan(heading) else 0))

            self._ready_to_move = lambda s: coordinates.distance(s.position) <= tolerance
            logger.debug(f"Waiting to reach destination (tolerance={tolerance}m)...")
            await wait_for_condition(lambda: self._ready_to_move(self), poll_interval=POLLING_DELAY_S,
                                     timeout=300, timeout_message=f"Failed to reach target within 300s")
            logger.debug(f"Arrived at destination, distance: {coordinates.distance(self.position)}m")
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
        Set a drone's velocity that it will use for `duration` seconds.

        Args:
            velocity_vector: Velocity in NED frame (m/s)
            global_relative: If True, vector is in global frame; if False, in body frame
            duration: How long to maintain velocity (None = until changed)

        Raises:
            VelocityError: If velocity command fails
        """
        logger.debug(f"set_velocity({velocity_vector}, global={global_relative}, duration={duration})")
        await self.await_ready_to_move()
        self._velocity_loop_active = False; await asyncio.sleep(POLLING_DELAY_S)

        if not global_relative:
            velocity_vector = velocity_vector.rotate_by_angle(-self.heading)
            logger.debug(f"Rotated velocity to global frame: {velocity_vector}")

        yaw = self._current_heading if self._current_heading is not None else self.heading

        try:
            logger.debug(f"Setting velocity NED: {velocity_vector}, yaw={yaw}")
            await self._run_on_mavsdk_loop(self._system.offboard.set_velocity_ned(
                    VelocityNedYaw(velocity_vector.north, velocity_vector.east, velocity_vector.down, yaw)))
            try: await self._run_on_mavsdk_loop(self._system.offboard.start())
            except OffboardError: pass

            self._ready_to_move = lambda _: True
            target_end = time.time() + duration if duration is not None else None

            async def _velocity_helper():
                while self._velocity_loop_active:
                    if target_end and time.time() > target_end:
                        self._velocity_loop_active = False
                        logger.debug("Stopping offboard mode (velocity duration ended)")
                        await self._run_on_mavsdk_loop(self._system.offboard.stop())
                    await asyncio.sleep(VELOCITY_UPDATE_DELAY_S)

            self._velocity_loop_active = True; asyncio.ensure_future(_velocity_helper())
        except (OffboardError, ActionError) as e: raise VelocityError(str(e), original_error=e)

    async def _stop(self) -> None:
        await super()._stop()
        self._velocity_loop_active = False
