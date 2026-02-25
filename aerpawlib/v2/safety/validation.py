"""
Preflight checks for aerpawlib v2.

Integrated into vehicle lifecycle.
"""

from __future__ import annotations

from ..logging import LogComponent, get_logger
from ..protocols import VehicleProtocol

logger = get_logger(LogComponent.SAFETY)


class PreflightChecks:
    """Preflight checks run before arm/takeoff."""

    @staticmethod
    async def check_gps_fix(vehicle: VehicleProtocol) -> bool:
        """Require 3D GPS fix."""
        if vehicle.gps.fix_type >= 3:
            return True
        logger.warning("Preflight: No 3D GPS fix")
        return False

    @staticmethod
    async def check_battery(vehicle: VehicleProtocol, min_percent: float = 10.0) -> bool:
        """Require minimum battery."""
        if vehicle.battery.level >= min_percent:
            return True
        logger.warning(f"Preflight: Battery {vehicle.battery.level}% below {min_percent}%")
        return False

    @staticmethod
    async def run_all(vehicle: VehicleProtocol) -> bool:
        """Run all preflight checks. Returns True if all pass."""
        gps_ok = await PreflightChecks.check_gps_fix(vehicle)
        bat_ok = await PreflightChecks.check_battery(vehicle)
        return gps_ok and bat_ok
