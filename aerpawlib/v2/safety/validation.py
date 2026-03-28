"""
Preflight checks for aerpawlib v2.

Integrated into vehicle lifecycle.
"""

from __future__ import annotations

from ..constants import DEFAULT_MIN_BATTERY_PERCENT, GPS_3D_FIX_TYPE
from ..log import LogComponent, get_logger
from ..protocols import VehicleProtocol

logger = get_logger(LogComponent.SAFETY)


class PreflightChecks:
    """Preflight checks run before arm/takeoff."""

    @staticmethod
    def check_gps_fix(vehicle: VehicleProtocol) -> bool:
        """Check that the vehicle has a 3D GPS fix.

        Args:
            vehicle: Vehicle to inspect.

        Returns:
            True if fix_type >= GPS_3D_FIX_TYPE, False otherwise.
        """
        if vehicle.gps.fix_type >= GPS_3D_FIX_TYPE:
            logger.debug(
                f"Preflight: GPS OK (fix_type={vehicle.gps.fix_type}, sats={vehicle.gps.satellites_visible})"
            )
            return True
        logger.warning(
            f"Preflight: No 3D GPS fix (fix_type={vehicle.gps.fix_type}, sats={vehicle.gps.satellites_visible})"
        )
        return False

    @staticmethod
    def check_battery(
        vehicle: VehicleProtocol, min_percent: float = DEFAULT_MIN_BATTERY_PERCENT
    ) -> bool:
        """Check that the vehicle battery is above the minimum threshold.

        Args:
            vehicle: Vehicle to inspect.
            min_percent: Minimum acceptable battery percentage (default 10.0).

        Returns:
            True if battery level >= min_percent, False otherwise.
        """
        if vehicle.battery.level >= min_percent:
            logger.debug(
                f"Preflight: Battery OK ({vehicle.battery.level}% >= {min_percent}%)"
            )
            return True
        logger.warning(
            f"Preflight: Battery {vehicle.battery.level}% below {min_percent}%"
        )
        return False

    @staticmethod
    async def run_all(vehicle: VehicleProtocol) -> bool:
        """Run all preflight checks and return True only if every check passes.

        Args:
            vehicle: Vehicle to run checks against.

        Returns:
            True if all checks pass, False if any check fails.
        """
        logger.info("PreflightChecks: running all checks")
        gps_ok = PreflightChecks.check_gps_fix(vehicle)
        bat_ok = PreflightChecks.check_battery(vehicle)
        passed = gps_ok and bat_ok
        logger.info(
            f"PreflightChecks: gps={gps_ok}, battery={bat_ok}, all_pass={passed}"
        )
        return passed
