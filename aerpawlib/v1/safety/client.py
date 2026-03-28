"""ZMQ client for SafetyCheckerServer."""

from typing import Dict, Tuple

import zmq

from aerpawlib.log import LogComponent, get_logger

from ..constants import (
    SAFETY_CHECKER_REQUEST_TIMEOUT_S,
    SERVER_STATUS_REQ,
    VALIDATE_CHANGE_SPEED_REQ,
    VALIDATE_LANDING_REQ,
    VALIDATE_TAKEOFF_REQ,
    VALIDATE_WAYPOINT_REQ,
)
from ..util import Coordinate
from .wire_format import deserialize_msg, serialize_request

logger = get_logger(LogComponent.SAFETY)


class SafetyCheckerClient:
    """
    A client for communicating with the SafetyCheckerServer via ZMQ.

    Attributes:
        context: The ZMQ context.
        socket: The REQ socket for sending requests.
    """

    def __init__(
        self,
        addr: str,
        port: int,
        timeout_s: float = SAFETY_CHECKER_REQUEST_TIMEOUT_S,
    ):
        """
        Initialize the safety checker client.

        Args:
            addr: The IP address of the safety checker server.
            port: The port the server is listening on.
            timeout_s: Timeout for send/recv in seconds. Prevents indefinite
                block if server is down. Defaults to SAFETY_CHECKER_REQUEST_TIMEOUT_S.
        """
        self._timeout_s = timeout_s
        self._addr = addr
        self._port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        timeout_ms = int(timeout_s * 1000)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        self.socket.connect(f"tcp://{addr}:{port}")

    def close(self) -> None:
        """Close the ZMQ socket and context to free resources."""
        self.socket.close()
        self.context.term()

    def _reconnect(self):
        """Recreate the ZMQ REQ socket to restore a clean send state after an error."""
        try:
            self.socket.close()
        except Exception:
            pass
        self.socket = self.context.socket(zmq.REQ)
        timeout_ms = int(self._timeout_s * 1000)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        self.socket.connect(f"tcp://{self._addr}:{self._port}")

    def __enter__(self) -> "SafetyCheckerClient":
        return self

    def __exit__(self, *_exc) -> bool:
        self.close()
        return False

    def send_request(self, msg: bytes) -> Dict:
        """
        Generic function to send a request to the safety checker server.

        Sends the provided raw message, then deserializes the response.

        Args:
            msg: The serialized request message.

        Returns:
            dict: The deserialized response from the server.

        Raises:
            TimeoutError: If the server does not respond within the configured timeout.
        """
        try:
            self.socket.send(msg)
            raw_msg = self.socket.recv()
        except zmq.Again:
            self._reconnect()
            raise TimeoutError(
                f"Safety checker server did not respond within {self._timeout_s}s"
            )
        message = deserialize_msg(raw_msg)
        logger.debug(f"Received reply [{message}]")
        return message

    def sendRequest(self, msg: bytes) -> Dict:
        """Backward-compatible alias for :meth:`send_request`."""
        return self.send_request(msg)

    def parse_response(self, response: Dict) -> Tuple[bool, str]:
        """
        Parse a response dictionary from the safety checker server.

        Args:
            response: The response dictionary to parse.

        Returns:
            Tuple[bool, str]: A tuple containing (result, message).
        """
        return response["result"], response["message"]

    def parseResponse(self, response: Dict) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`parse_response`."""
        return self.parse_response(response)

    def check_server_status(self) -> Tuple[bool, str]:
        """
        Verify the safety checker server is reachable and active.

        Returns:
            Tuple[bool, str]: A tuple containing (True, "") if server is up.
        """
        msg = serialize_request(SERVER_STATUS_REQ, [])
        resp = self.send_request(msg)
        return self.parse_response(resp)

    def checkServerStatus(self) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`check_server_status`."""
        return self.check_server_status()

    def validate_waypoint_command(
        self, current_location: Coordinate, next_location: Coordinate
    ) -> Tuple[bool, str]:
        """
        Makes sure path from current location to next waypoint stays inside geofence and avoids no-go zones.
        Returns a tuple (bool, str)
        (False, <error message>) if the waypoint violates geofence or no-go zone constraints, else (True, "").
        """
        msg = serialize_request(
            VALIDATE_WAYPOINT_REQ,
            [current_location.to_json(), next_location.to_json()],
        )
        resp = self.send_request(msg)
        return self.parse_response(resp)

    def validateWaypointCommand(
        self, curLoc: Coordinate, nextLoc: Coordinate
    ) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`validate_waypoint_command`."""
        return self.validate_waypoint_command(curLoc, nextLoc)

    def validate_change_speed_command(self, new_speed: float) -> Tuple[bool, str]:
        """
        Makes sure the provided new_speed lies within the configured vehicle constraints
        Returns (False, <error message>) if the speed violates constraints, else (True, "").
        """
        msg = serialize_request(VALIDATE_CHANGE_SPEED_REQ, [new_speed])
        resp = self.send_request(msg)
        return self.parse_response(resp)

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
        msg = serialize_request(
            VALIDATE_TAKEOFF_REQ, [takeoff_alt, current_lat, current_lon]
        )
        resp = self.send_request(msg)
        return self.parse_response(resp)

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
        msg = serialize_request(VALIDATE_LANDING_REQ, [current_lat, current_lon])
        resp = self.send_request(msg)
        return self.parse_response(resp)

    def validateLandingCommand(
        self, currentLat: float, currentLon: float
    ) -> Tuple[bool, str]:
        """Backward-compatible alias for :meth:`validate_landing_command`."""
        return self.validate_landing_command(currentLat, currentLon)
