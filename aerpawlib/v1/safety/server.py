"""
ZMQ safety server and geofence validation utilities.

This module implements `SafetyCheckerServer`, a blocking REP server that loads
vehicle constraints from configuration and validates incoming command requests.

Capabilities:
- Validate waypoint paths against include/exclude geofence polygons.
- Validate speed and altitude constraints for supported vehicle types.
- Reply with structured pass/fail responses over the compressed wire format.

Usage:
- Run the server as a sidecar process and point `SafetyCheckerClient` instances
  at its host/port.

Notes:
- Request payloads use the compressed JSON format defined in
  `aerpawlib.v1.safety.wire_format`.
"""

from __future__ import annotations

import json
import math
from argparse import ArgumentParser
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import yaml
import zmq

from aerpawlib.v1.constants import (
    DEFAULT_MAX_VERTICAL_SPEED_M_S,
    DEFAULT_SAFETY_SERVER_PORT,
    GET_LIMITATIONS_REQ,
    SERVER_STATUS_REQ,
    VALIDATE_CHANGE_SPEED_REQ,
    VALIDATE_LANDING_REQ,
    VALIDATE_TAKEOFF_REQ,
    VALIDATE_WAYPOINT_REQ,
    VEHICLE_TYPE_COPTER,
)
from aerpawlib.v1.log import LogComponent, get_logger
from aerpawlib.v1.util import Coordinate, do_intersect, inside, read_geofence

from .wire_format import deserialize_msg, serialize_response

logger = get_logger(LogComponent.SAFETY)


def _all_finite(*values: Any) -> bool:
    """True when every value is a real, finite number (NaN compares false to every limit)."""
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


# noinspection PyUnusedLocal
class SafetyCheckerServer:
    """
    A server that validates vehicle commands against geofences and constraints.

    Attributes:
        REQUEST_FUNCTIONS: Mapping of request types to handler methods.
        vehicle_type: Type of vehicle ('copter' or 'rover').
        include_geofences: List of allowed regions.
        exclude_geofences: List of no-go zones.
        max_speed: Maximum allowed speed (m/s).
        min_speed: Minimum allowed speed (m/s).
        max_alt: Maximum allowed altitude for copters.
        min_alt: Minimum allowed altitude for copters.
        max_vertical_speed: Maximum climb/descent velocity for copters (m/s);
            optional in the config, DEFAULT_MAX_VERTICAL_SPEED_M_S if unset.
        takeoff_location: The location where takeoff was performed.
    """

    VEHICLE_TYPES: ClassVar[list[str]] = ["rover", "copter"]
    REQUIRED_PARAMS: ClassVar[list[str]] = [
        "vehicle_type",
        "max_speed",
        "min_speed",
        "include_geofences",
        "exclude_geofences",
    ]
    REQUIRED_COPTER_PARAMS: ClassVar[list[str]] = ["max_alt", "min_alt"]

    def __init__(
        self,
        vehicle_config_filename: str,
        server_port: int = DEFAULT_SAFETY_SERVER_PORT,
    ) -> None:
        """
        Initialize the safety checker server and start listening.

        Args:
            vehicle_config_filename: Path to the YAML configuration file.
            server_port: Port to bind the server to. Defaults to
                DEFAULT_SAFETY_SERVER_PORT.
        """
        self.REQUEST_FUNCTIONS = {
            SERVER_STATUS_REQ: self.server_status_handler,
            VALIDATE_WAYPOINT_REQ: self.validate_waypoint_handler,
            VALIDATE_CHANGE_SPEED_REQ: self.validate_change_speed_handler,
            VALIDATE_TAKEOFF_REQ: self.validate_takeoff_handler,
            VALIDATE_LANDING_REQ: self.validate_landing_handler,
            GET_LIMITATIONS_REQ: self.get_limitations_handler,
        }

        config_path = Path(vehicle_config_filename)
        with config_path.open(encoding="utf-8") as vehicle_config_file:
            config = yaml.safe_load(vehicle_config_file)

        self.validate_config(config, str(config_path))

        self.vehicle_type = config["vehicle_type"]

        vehicle_config_dir = config_path.parent
        self.include_geofences = [read_geofence(str(vehicle_config_dir / geofence)) for geofence in config["include_geofences"]]
        self.exclude_geofences = [read_geofence(str(vehicle_config_dir / geofence)) for geofence in config["exclude_geofences"]]
        self.max_speed = config["max_speed"]
        self.min_speed = config["min_speed"]

        self.takeoff_location = None

        if self.vehicle_type == VEHICLE_TYPE_COPTER:
            self.max_alt = config["max_alt"]
            self.min_alt = config["min_alt"]
            self.max_vertical_speed = config.get("max_vertical_speed", DEFAULT_MAX_VERTICAL_SPEED_M_S)

        self.start_server(server_port)

    def start_server(
        self,
        port: int,
        *,
        context_factory: Callable[[], Any] | None = None,
    ) -> None:
        """
        Start the ZMQ server loop. Blocks until the program is terminated.

        Args:
            port: The port to bind to.
            context_factory: Optional callable returning a ZMQ-like context with
                ``socket(type)`` and ``term()`` (for tests). Defaults to
                ``zmq.Context``.
        """
        ctx_factory = zmq.Context if context_factory is None else context_factory
        context = ctx_factory()
        socket = context.socket(zmq.REP)
        socket.bind(f"tcp://*:{port}")

        logger.info("waiting for messages")

        try:
            while True:
                function_name = "unknown"
                try:
                    raw_msg = socket.recv()
                    message = deserialize_msg(raw_msg)
                    logger.debug(f"Received ZMQ message: {message}")
                    function_name = message.get("request_function", "unknown")
                    req_function = self.REQUEST_FUNCTIONS[function_name]
                    params = message.get("params")
                    if params is None:
                        response = req_function()
                    else:
                        response = req_function(*params)
                    socket.send(response)
                except KeyError:
                    error_resp = serialize_response(
                        request_function=function_name,
                        result=False,
                        message=(f"Unimplemented or missing function request <{function_name}>"),
                    )
                    socket.send(error_resp)
                except Exception as e:
                    logger.debug("Safety checker server handler error: %s", e)
                    error_resp = serialize_response(
                        request_function="unknown",
                        result=False,
                        message=f"Server error: {e}",
                    )
                    socket.send(error_resp)
        finally:
            socket.close()
            context.term()

    def validate_config(self, config: dict, vehicle_config_filename: str) -> None:
        """
        Ensures that the provided config dict contains all necessary parameters.

        Args:
            config: The configuration dictionary loaded from YAML.
            vehicle_config_filename: Filename for error reporting.

        Raises:
            Exception: If the configuration is invalid or missing required keys.
        """
        for param in self.REQUIRED_PARAMS:
            if param not in config:
                raise Exception(
                    f"Required parameter {param} not found in {vehicle_config_filename}!",
                )

        if config["vehicle_type"] not in self.VEHICLE_TYPES:
            raise Exception(
                f"Vehicle type in {vehicle_config_filename} is invalid! Must be one of {self.VEHICLE_TYPES}",
            )

        if config["vehicle_type"] == VEHICLE_TYPE_COPTER:
            for param in self.REQUIRED_COPTER_PARAMS:
                if param not in config:
                    raise Exception(
                        f"Required copter parameter {param} not found in {vehicle_config_filename}!",
                    )

        # NaN limits compare false against everything and would allow any value.
        pairs = [("min_speed", "max_speed")]
        if config["vehicle_type"] == VEHICLE_TYPE_COPTER:
            pairs.append(("min_alt", "max_alt"))
        for low, high in pairs:
            if not _all_finite(config[low], config[high]) or config[low] > config[high]:
                raise Exception(
                    f"{low}/{high} in {vehicle_config_filename} must be finite numbers with {low} <= {high}!",
                )
        if "max_vertical_speed" in config and not (_all_finite(config["max_vertical_speed"]) and config["max_vertical_speed"] > 0):
            raise Exception(
                f"max_vertical_speed in {vehicle_config_filename} must be a finite number > 0!",
            )

    def validate_waypoint_command(
        self,
        current_location: Coordinate,
        next_location: Coordinate,
        taking_off_or_landing: bool = False,
    ) -> tuple[bool, str]:
        """
        Makes sure path from current location to next waypoint stays inside
        geofence and avoids no-go zones. Returns a tuple (bool, str)
        (False, <error message>) if the waypoint violates geofence or no-go zone
        constraints, else (True, "").

        taking_off_or_landing skips only the altitude limits, for a copter
        climbing to or descending from cruise; geofence checks still run.
        """
        logger.debug(f"Validating {next_location}")

        if not _all_finite(current_location.lat, current_location.lon, next_location.lat, next_location.lon, next_location.alt):
            return False, "Invalid waypoint. Coordinates must be finite numbers. ABORTING!"

        if self.vehicle_type == VEHICLE_TYPE_COPTER and not taking_off_or_landing and (next_location.alt < self.min_alt or next_location.alt > self.max_alt):
            return (
                False,
                (f"Invalid waypoint. Altitude of {next_location.alt} m is not within restrictions! ABORTING!"),
            )

        dest_geofence = None
        for gf in self.include_geofences:
            if inside(next_location.lon, next_location.lat, gf):
                dest_geofence = gf
                break
        if dest_geofence is None:
            return (
                False,
                (f"Invalid waypoint. Waypoint ({next_location.lat},{next_location.lon}) is outside of the geofence. ABORTING!"),
            )
        for zone in self.exclude_geofences:
            if inside(next_location.lon, next_location.lat, zone):
                return (
                    False,
                    (f"Invalid waypoint. Waypoint ({next_location.lat},{next_location.lon}) is inside a no-go zone. ABORTING!"),
                )
        n = len(dest_geofence)
        for i in range(n):
            p1 = dest_geofence[i]
            p2 = dest_geofence[(i + 1) % n]
            if do_intersect(
                p1["lon"],
                p1["lat"],
                p2["lon"],
                p2["lat"],
                current_location.lon,
                current_location.lat,
                next_location.lon,
                next_location.lat,
            ):
                return (
                    False,
                    (f"Invalid waypoint. Path from ({current_location.lat},{current_location.lon}) to waypoint ({next_location.lat},{next_location.lon}) leaves geofence. ABORTING!"),
                )

        for zone in self.exclude_geofences:
            m = len(zone)
            for j in range(m):
                p1 = zone[j]
                p2 = zone[(j + 1) % m]
                if do_intersect(
                    p1["lon"],
                    p1["lat"],
                    p2["lon"],
                    p2["lat"],
                    current_location.lon,
                    current_location.lat,
                    next_location.lon,
                    next_location.lat,
                ):
                    return (
                        False,
                        (f"Invalid waypoint. Path from ({current_location.lat},{current_location.lon}) to waypoint ({next_location.lat},{next_location.lon}) enters no-go zone. ABORTING!"),
                    )

        return True, ""

    def _inside_fence(self, lon: float, lat: float) -> bool:
        """True when the point is inside an include fence and outside every no-go zone."""
        if not any(inside(lon, lat, gf) for gf in self.include_geofences):
            return False
        return not any(inside(lon, lat, zone) for zone in self.exclude_geofences)

    def validate_change_speed_command(self, new_speed: float) -> tuple[bool, str]:
        """
        Makes sure the provided newSpeed lies within the configured vehicle
        constraints. Returns (False, <error message>) if the speed violates
        constraints, else (True, "").
        """
        if not _all_finite(new_speed):
            return False, f"Invalid speed ({new_speed}); must be a finite number"
        if new_speed > self.max_speed:
            return (
                False,
                f"Invalid speed ({new_speed}) greater than maximum ({self.max_speed})",
            )
        if new_speed < self.min_speed:
            return (
                False,
                f"Invalid speed ({new_speed}) less than minimum ({self.min_speed})",
            )
        return True, ""

    def validate_takeoff_command(
        self,
        takeoff_alt: float,
        current_lat: float,
        current_lon: float,
    ) -> tuple[bool, str]:
        """
        Makes sure the takeoff altitude lies within the vehicle constraints.
        Returns (False, <error message>) if the altitude violates constraints,
        else (True, "").
        """
        if not _all_finite(takeoff_alt):
            return False, f"Invalid takeoff altitude of {takeoff_alt} m."
        if not _all_finite(current_lat, current_lon) or not self._inside_fence(current_lon, current_lat):
            return False, f"Invalid takeoff location ({current_lat},{current_lon}); must be inside the geofence."
        if self.vehicle_type == VEHICLE_TYPE_COPTER and (takeoff_alt < self.min_alt or takeoff_alt > self.max_alt):
            return (
                False,
                f"Invalid takeoff altitude of {takeoff_alt} m.",
            )
        # Pad is filter GPS at first forwarded armed NAV_TAKEOFF, not this ZMQ check.
        return True, ""

    def validate_landing_command(
        self,
        current_lat: float,
        current_lon: float,
    ) -> tuple[bool, str]:
        """
        Ensure the copter is attempting to land within 5 meters of the takeoff
        location. Returns (False, <error message>) if the copter is not within
        5 meters, else (True, "").
        """
        if not hasattr(self, "takeoff_location") or self.takeoff_location is None:
            return (
                True,
                "",
            )
        if not _all_finite(current_lat, current_lon):
            return False, f"Invalid landing location ({current_lat},{current_lon})."
        current_location = Coordinate(current_lat, current_lon, alt=0)
        distance = self.takeoff_location.ground_distance(current_location)

        if distance > 5:
            return (
                False,
                f"Invalid landing location. Must be within 5 meters of takeoff location. Attempted landing location ({current_lat},{current_lon}) is {distance:f} meters from takeoff location.",
            )
        return True, ""

    def get_limitations(self) -> dict:
        """
        Return the configured vehicle limits.

        Returns:
            dict: vehicle_type, min_speed, max_speed, max_vertical_speed,
            min_alt and max_alt (the last three are None for rovers).
        """
        is_copter = self.vehicle_type == VEHICLE_TYPE_COPTER
        return {
            "vehicle_type": self.vehicle_type,
            "min_speed": self.min_speed,
            "max_speed": self.max_speed,
            "max_vertical_speed": self.max_vertical_speed if is_copter else None,
            "min_alt": self.min_alt if is_copter else None,
            "max_alt": self.max_alt if is_copter else None,
        }

    def get_limitations_handler(self, *_params: Any) -> bytes:
        """
        Handler for vehicle limit requests.

        Returns:
            bytes: Serialized response with the limits in ``data``.
        """
        return serialize_response(
            request_function=GET_LIMITATIONS_REQ,
            result=True,
            data=self.get_limitations(),
        )

    def server_status_handler(self, *_params: Any) -> bytes:
        """
        Handler for server status requests.

        Returns:
            bytes: Serialized successful response.
        """
        return serialize_response(request_function=SERVER_STATUS_REQ, result=True)

    def validate_waypoint_handler(
        self,
        current_json_location: str,
        next_json_location: str,
        taking_off_or_landing: bool = False,
        *_params: Any,
    ) -> bytes:
        """
        Handler for waypoint validation requests.

        Args:
            current_json_location: JSON string representing the current Coordinate.
            next_json_location: JSON string representing the target Coordinate.
            taking_off_or_landing: Skip copter altitude limits (optional).

        Returns:
            bytes: Serialized validation response.
        """
        current_dict_location = json.loads(current_json_location)
        next_dict_location = json.loads(next_json_location)
        current_location = Coordinate(
            lat=current_dict_location["lat"],
            lon=current_dict_location["lon"],
            alt=current_dict_location["alt"],
        )
        next_location = Coordinate(
            lat=next_dict_location["lat"],
            lon=next_dict_location["lon"],
            alt=next_dict_location["alt"],
        )

        result, message = self.validate_waypoint_command(
            current_location,
            next_location,
            taking_off_or_landing=taking_off_or_landing is True,
        )
        return serialize_response(
            request_function=VALIDATE_WAYPOINT_REQ,
            result=result,
            message=message,
        )

    def validate_change_speed_handler(self, new_speed: float, *_params: Any) -> bytes:
        """
        Handler for speed change validation requests.

        Args:
            new_speed: The requested new speed.

        Returns:
            bytes: Serialized validation response.
        """
        result, message = self.validate_change_speed_command(new_speed)
        return serialize_response(
            request_function=VALIDATE_CHANGE_SPEED_REQ,
            result=result,
            message=message,
        )

    def validate_takeoff_handler(
        self,
        takeoff_alt: float,
        current_lat: float,
        current_lon: float,
        *_params: Any,
    ) -> bytes:
        """
        Handler for takeoff validation requests.

        Args:
            takeoff_alt: The requested takeoff altitude.
            current_lat: Current latitude.
            current_lon: Current longitude.

        Returns:
            bytes: Serialized validation response.
        """
        result, message = self.validate_takeoff_command(
            takeoff_alt,
            current_lat,
            current_lon,
        )
        return serialize_response(
            request_function=VALIDATE_TAKEOFF_REQ,
            result=result,
            message=message,
        )

    def validate_landing_handler(
        self,
        current_lat: float,
        current_lon: float,
        *_params: Any,
    ) -> bytes:
        """
        Handler for landing validation requests.

        Args:
            current_lat: Current latitude.
            current_lon: Current longitude.

        Returns:
            bytes: Serialized validation response.
        """
        result, message = self.validate_landing_command(current_lat, current_lon)
        return serialize_response(
            request_function=VALIDATE_LANDING_REQ,
            result=result,
            message=message,
        )


def main_cli() -> None:
    """CLI entry for launching the safety checker server (legacy interface)."""
    parser = ArgumentParser(description="safety - Launch a safety server")
    parser.add_argument(
        "--port",
        help="Port for communication between client and server",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--vehicle_config",
        help="Path to YAML file containing geofences and vehicle constraints",
        required=True,
    )
    args, _ = parser.parse_known_args()

    SafetyCheckerServer(args.vehicle_config, server_port=args.port)


# Backward-compatible camelCase aliases.
SafetyCheckerServer.validateWaypointCommand = SafetyCheckerServer.validate_waypoint_command
SafetyCheckerServer.validateChangeSpeedCommand = SafetyCheckerServer.validate_change_speed_command
SafetyCheckerServer.validateTakeoffCommand = SafetyCheckerServer.validate_takeoff_command
SafetyCheckerServer.validateLandingCommand = SafetyCheckerServer.validate_landing_command
SafetyCheckerServer.getLimitations = SafetyCheckerServer.get_limitations
SafetyCheckerServer.serverStatusHandler = SafetyCheckerServer.server_status_handler
SafetyCheckerServer.validateWaypointHandler = SafetyCheckerServer.validate_waypoint_handler
SafetyCheckerServer.validateChangeSpeedHandler = SafetyCheckerServer.validate_change_speed_handler
SafetyCheckerServer.validateTakeoffHandler = SafetyCheckerServer.validate_takeoff_handler
SafetyCheckerServer.validateLandingHandler = SafetyCheckerServer.validate_landing_handler


if __name__ == "__main__":
    main_cli()
