"""ZMQ SafetyCheckerServer and geofence validation."""

import json
import os
from argparse import ArgumentParser
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import yaml
import zmq

from aerpawlib.log import LogComponent, get_logger

from ..constants import (
    SERVER_STATUS_REQ,
    VALIDATE_CHANGE_SPEED_REQ,
    VALIDATE_LANDING_REQ,
    VALIDATE_TAKEOFF_REQ,
    VALIDATE_WAYPOINT_REQ,
    VEHICLE_TYPE_COPTER,
    VEHICLE_TYPE_ROVER,
    DEFAULT_SAFETY_SERVER_PORT,
)
from ..util import Coordinate, do_intersect, inside, read_geofence
from .wire_format import deserialize_msg, serialize_response

logger = get_logger(LogComponent.SAFETY)


def _polygon_edges(
    polygon: List[Dict[str, float]],
) -> Iterator[Tuple[Dict[str, float], Dict[str, float]]]:
    """
    Yield consecutive (p1, p2) edge pairs for a polygon, including the
    closing edge from the last vertex back to the first.

    Args:
        polygon: List of {'lat': ..., 'lon': ...} points.

    Yields:
        Tuple[dict, dict]: Pairs of adjacent vertices.
    """
    n = len(polygon)
    for i in range(n):
        yield polygon[i], polygon[(i + 1) % n]


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
        takeoff_location: The location where takeoff was performed.
    """

    VEHICLE_TYPES = ["rover", "copter"]
    REQUIRED_PARAMS = [
        "vehicle_type",
        "max_speed",
        "min_speed",
        "include_geofences",
        "exclude_geofences",
    ]
    REQUIRED_COPTER_PARAMS = ["max_alt", "min_alt"]

    def __init__(
        self,
        vehicle_config_filename: str,
        server_port: int = DEFAULT_SAFETY_SERVER_PORT,
    ) -> None:
        """
        Initialize the safety checker server and start listening.

        Args:
            vehicle_config_filename: Path to the YAML configuration file.
            server_port: Port to bind the server to. Defaults to DEFAULT_SAFETY_SERVER_PORT.
        """
        self.REQUEST_FUNCTIONS = {
            SERVER_STATUS_REQ: self.server_status_handler,
            VALIDATE_WAYPOINT_REQ: self.validate_waypoint_handler,
            VALIDATE_CHANGE_SPEED_REQ: self.validate_change_speed_handler,
            VALIDATE_TAKEOFF_REQ: self.validate_takeoff_handler,
            VALIDATE_LANDING_REQ: self.validate_landing_handler,
        }

        with open(vehicle_config_filename, "r") as vehicle_config_file:
            config = yaml.safe_load(vehicle_config_file)

        self.validate_config(config, vehicle_config_filename)

        self.vehicle_type = config["vehicle_type"]

        vehicle_config_dir, _ = os.path.split(vehicle_config_filename)
        self.include_geofences = [
            read_geofence(os.path.join(vehicle_config_dir, geofence))
            for geofence in config["include_geofences"]
        ]
        self.exclude_geofences = [
            read_geofence(os.path.join(vehicle_config_dir, geofence))
            for geofence in config["exclude_geofences"]
        ]
        self.max_speed = config["max_speed"]
        self.min_speed = config["min_speed"]

        self.takeoff_location = None

        if self.vehicle_type == VEHICLE_TYPE_COPTER:
            self.max_alt = config["max_alt"]
            self.min_alt = config["min_alt"]

        self.start_server(server_port)

    def start_server(
        self,
        port: int,
        *,
        context_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        """
        Start the ZMQ server loop. Blocks until the program is terminated.

        Args:
            port: The port to bind to.
            context_factory: Optional callable returning a ZMQ-like context with
                ``socket(type)`` and ``term()`` (for tests). Defaults to ``zmq.Context``.
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
                    logger.debug(f"Received request: {message}")
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
                        message=(
                            "Unimplemented or missing function request "
                            f"<{function_name}>"
                        ),
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

    def validate_config(self, config: Dict, vehicle_config_filename: str) -> None:
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
                    f"Required parameter {param} not found in {vehicle_config_filename}!"
                )

        if config["vehicle_type"] not in self.VEHICLE_TYPES:
            raise Exception(
                f"Vehicle type in {vehicle_config_filename} is invalid! Must be one of {self.VEHICLE_TYPES}"
            )

        if config["vehicle_type"] == VEHICLE_TYPE_COPTER:
            for param in self.REQUIRED_COPTER_PARAMS:
                if param not in config:
                    raise Exception(
                        f"Required copter parameter {param} not found in {vehicle_config_filename}!"
                    )

    def validate_waypoint_command(
        self, current_location: Coordinate, next_location: Coordinate
    ) -> Tuple[bool, str]:
        """
        Makes sure path from current location to next waypoint stays inside geofence and avoids no-go zones.
        Returns a tuple (bool, str)
        (False, <error message>) if the waypoint violates geofence or no-go zone constraints, else (True, "").
        """
        logger.debug(f"Validating {next_location}")

        if self.vehicle_type == VEHICLE_TYPE_COPTER:
            if next_location.alt < self.min_alt or next_location.alt > self.max_alt:
                return (
                    False,
                    "Invalid waypoint. Altitude of %s m is not within restrictions! ABORTING!"
                    % next_location.alt,
                )

        dest_geofence = None
        for gf in self.include_geofences:
            if inside(next_location.lon, next_location.lat, gf):
                dest_geofence = gf
                break
        if dest_geofence is None:
            return (
                False,
                "Invalid waypoint. Waypoint (%s,%s) is outside of the geofence. ABORTING!"
                % (next_location.lat, next_location.lon),
            )
        for zone in self.exclude_geofences:
            if inside(next_location.lon, next_location.lat, zone):
                return (
                    False,
                    "Invalid waypoint. Waypoint (%s,%s) is inside a no-go zone. ABORTING!"
                    % (next_location.lat, next_location.lon),
                )
        for p1, p2 in _polygon_edges(dest_geofence):
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
                    "Invalid waypoint. Path from (%s,%s) to waypoint (%s,%s) leaves geofence. ABORTING!"
                    % (
                        current_location.lat,
                        current_location.lon,
                        next_location.lat,
                        next_location.lon,
                    ),
                )

        for zone in self.exclude_geofences:
            for p1, p2 in _polygon_edges(zone):
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
                        "Invalid waypoint. Path from (%s,%s) to waypoint (%s,%s) enters no-go zone. ABORTING!"
                        % (
                            current_location.lat,
                            current_location.lon,
                            next_location.lat,
                            next_location.lon,
                        ),
                    )

        return True, ""

    def validateWaypointCommand(
        self, curLoc: Coordinate, nextLoc: Coordinate
    ) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`validate_waypoint_command`."""
        return self.validate_waypoint_command(curLoc, nextLoc)

    def validate_change_speed_command(self, new_speed: float) -> Tuple[bool, str]:
        """
        Makes sure the provided newSpeed lies within the configured vehicle constraints
        Returns (False, <error message>) if the speed violates constraints, else (True, "").
        """
        if new_speed > self.max_speed:
            return (
                False,
                "Invalid speed (%s) greater than maximum (%s)"
                % (new_speed, self.max_speed),
            )
        if new_speed < self.min_speed:
            return (
                False,
                "Invalid speed (%s) less than minimum (%s)"
                % (new_speed, self.min_speed),
            )
        return True, ""

    def validateChangeSpeedCommand(self, newSpeed: float) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`validate_change_speed_command`."""
        return self.validate_change_speed_command(newSpeed)

    def validate_takeoff_command(
        self, takeoff_alt: float, current_lat: float, current_lon: float
    ) -> Tuple[bool, str]:
        """
        Makes sure the takeoff altitude lies within the vehicle constraints
        Returns (False, <error message>) if the altitude violates constraints, else (True, "").
        """
        if self.vehicle_type == VEHICLE_TYPE_COPTER:
            if takeoff_alt < self.min_alt or takeoff_alt > self.max_alt:
                return (
                    False,
                    "Invalid takeoff altitude of %s m." % takeoff_alt,
                )
        self.takeoff_location = Coordinate(current_lat, current_lon, alt=0)
        return True, ""

    def validateTakeoffCommand(
        self, takeoffAlt: float, currentLat: float, currentLon: float
    ) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`validate_takeoff_command`."""
        return self.validate_takeoff_command(takeoffAlt, currentLat, currentLon)

    def validate_landing_command(
        self, current_lat: float, current_lon: float
    ) -> Tuple[bool, str]:
        """
        Ensure the copter is attempting to land within 5 meters of the takeoff location
        Returns (False, <error message>) if the coper is not within 5 meters, else (True, "").
        """
        if not hasattr(self, "takeoff_location") or self.takeoff_location is None:
            return (
                False,
                "Cannot validate landing: no takeoff location recorded. "
                "Was validate_takeoff_command called first?",
            )
        current_location = Coordinate(current_lat, current_lon, alt=0)
        distance = self.takeoff_location.ground_distance(current_location)

        if distance > 5:
            return (
                False,
                "Invalid landing location. Must be within 5 meters of takeoff location. Attempted landing location (%s,%s) is %f meters from takeoff location."
                % (current_lat, current_lon, distance),
            )
        return True, ""

    def validateLandingCommand(
        self, currentLat: float, currentLon: float
    ) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`validate_landing_command`."""
        return self.validate_landing_command(currentLat, currentLon)

    def server_status_handler(self, *_params: Any) -> bytes:
        """
        Handler for server status requests.

        Returns:
            bytes: Serialized successful response.
        """
        msg = serialize_response(request_function=SERVER_STATUS_REQ, result=True)
        return msg

    def serverStatusHandler(self, *_params: Any) -> bytes:
        """Backward-compatible alias for :meth:`server_status_handler`."""
        return self.server_status_handler(*_params)

    def validate_waypoint_handler(
        self, current_json_location: str, next_json_location: str, *_params: Any
    ) -> bytes:
        """
        Handler for waypoint validation requests.

        Args:
            current_json_location: JSON string representing the current Coordinate.
            next_json_location: JSON string representing the target Coordinate.

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
            current_location, next_location
        )
        msg = serialize_response(
            request_function=VALIDATE_WAYPOINT_REQ,
            result=result,
            message=message,
        )
        return msg

    def validateWaypointHandler(
        self, curLocJSON: str, nextLocJSON: str, *_params: Any
    ) -> bytes:
        """Backward-compatible alias for :meth:`validate_waypoint_handler`."""
        return self.validate_waypoint_handler(curLocJSON, nextLocJSON, *_params)

    def validate_change_speed_handler(self, new_speed: float, *_params: Any) -> bytes:
        """
        Handler for speed change validation requests.

        Args:
            new_speed: The requested new speed.

        Returns:
            bytes: Serialized validation response.
        """
        result, message = self.validate_change_speed_command(new_speed)
        msg = serialize_response(
            request_function=VALIDATE_CHANGE_SPEED_REQ,
            result=result,
            message=message,
        )
        return msg

    def validateChangeSpeedHandler(self, newSpeed: float, *_params: Any) -> bytes:
        """Backward-compatible alias for :meth:`validate_change_speed_handler`."""
        return self.validate_change_speed_handler(newSpeed, *_params)

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
            takeoff_alt, current_lat, current_lon
        )
        msg = serialize_response(
            request_function=VALIDATE_TAKEOFF_REQ,
            result=result,
            message=message,
        )
        return msg

    def validateTakeoffHandler(
        self,
        takeoffAlt: float,
        currentLat: float,
        currentLon: float,
        *_params: Any,
    ) -> bytes:
        """Backward-compatible alias for :meth:`validate_takeoff_handler`."""
        return self.validate_takeoff_handler(
            takeoffAlt, currentLat, currentLon, *_params
        )

    def validate_landing_handler(
        self, current_lat: float, current_lon: float, *_params: Any
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
        msg = serialize_response(
            request_function=VALIDATE_LANDING_REQ,
            result=result,
            message=message,
        )
        return msg

    def validateLandingHandler(
        self, currentLat: float, currentLon: float, *_params: Any
    ) -> bytes:
        """Backward-compatible alias for :meth:`validate_landing_handler`."""
        return self.validate_landing_handler(currentLat, currentLon, *_params)


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
