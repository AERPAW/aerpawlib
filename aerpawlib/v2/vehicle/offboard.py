"""Shared offboard session state for Drone and Rover."""

from __future__ import annotations

import contextlib
import logging

from mavsdk.offboard import OffboardError, VelocityNedYaw

logger = logging.getLogger(__name__)


class OffboardSession:
    """Tracks offboard mode and velocity-loop lifecycle for movement commands."""

    def __init__(self) -> None:
        self.active: bool = False
        self.velocity_loop_active: bool = False

    async def stop(self, system, heading: float = 0.0, *, closed: bool = False) -> None:
        """Stop offboard mode and zero the velocity setpoint."""
        self.velocity_loop_active = False
        self.active = False
        if closed or system is None:
            logger.debug("OffboardSession.stop: skipped (vehicle closed)")
            return
        try:
            await system.offboard.set_velocity_ned(VelocityNedYaw(0, 0, 0, heading))
            await system.offboard.stop()
        except Exception:
            logger.debug("OffboardSession.stop: offboard may not be active")

    async def start_velocity(
        self,
        system,
        north: float,
        east: float,
        down: float,
        yaw: float,
    ) -> None:
        """Enter offboard mode with a NED velocity setpoint."""
        await system.offboard.set_velocity_ned(
            VelocityNedYaw(north, east, down, yaw),
        )
        with contextlib.suppress(OffboardError):
            await system.offboard.start()
        self.active = True
