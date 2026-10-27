"""
ZMQ client for the v1 `SafetyCheckerServer`.

This module implements the REQ/REP client used by vehicle code to submit
safety validation requests to the checker server.

Capabilities:
- Submit waypoint, speed, takeoff, landing, velocity, and GUIDED-command
  validation requests.
- Report the C-VM filter's landing pad and takeovers (used by the filter).
- Serialize requests using the safety wire format helpers.
- Use bounded send/receive timeouts to avoid indefinite blocking.

Usage:
- Instantiate `SafetyCheckerClient` with server address/port and call the
  validation helper methods before issuing movement commands.
"""

import contextlib
import threading

import zmq

from aerpawlib.v1.constants import (
    GET_FILTER_STATUS_REQ,
    GET_LIMITATIONS_REQ,
    REPORT_FILTER_ABORT_REQ,
    REPORT_TAKEOFF_LOCATION_REQ,
    REPORT_TAKEOVER_REQ,
    SAFETY_CHECKER_REQUEST_TIMEOUT_S,
    SERVER_STATUS_REQ,
    VALIDATE_CHANGE_SPEED_REQ,
    VALIDATE_GUIDED_COMMAND_REQ,
    VALIDATE_LANDING_REQ,
    VALIDATE_TAKEOFF_REQ,
    VALIDATE_VELOCITY_REQ,
    VALIDATE_WAYPOINT_REQ,
)
from aerpawlib.v1.log import LogComponent, get_logger
from aerpawlib.v1.util import Coordinate, VectorNED

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
        # One REQ socket: concurrent callers (a velocity stream and a goto)
        # would break its strict send/recv order.
        self._lock = threading.Lock()
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        timeout_ms = int(timeout_s * 1000)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        self.socket.connect(f"tcp://{addr}:{port}")

    def close(self) -> None:
        """Close the ZMQ socket and context to free resources."""
        # linger=0: queued requests to a wedged server must not block term().
        self.socket.close(linger=0)
        self.context.term()

    def _reconnect(self):
        """Recreate the ZMQ REQ socket to restore a clean send state after an error."""
        with contextlib.suppress(Exception):
            self.socket.close(linger=0)
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

    def send_request(self, msg: bytes) -> dict:
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
        with self._lock:
            try:
                self.socket.send(msg)
                raw_msg = self.socket.recv()
            except zmq.Again as e:
                self._reconnect()
                raise TimeoutError(
                    f"Safety checker server did not respond within {self._timeout_s}s",
                ) from e
        message = deserialize_msg(raw_msg)
        logger.debug(f"Received ZMQ message: {message}")
        return message

    def parse_response(self, response: dict) -> tuple[bool, str]:
        """
        Parse a response dictionary from the safety checker server.

        Args:
            response: The response dictionary to parse.

        Returns:
            Tuple[bool, str]: A tuple containing (result, message).
        """
        return response["result"], response["message"]

    def check_server_status(self) -> tuple[bool, str]:
        """
        Verify the safety checker server is reachable and active.

        Returns:
            Tuple[bool, str]: A tuple containing (True, "") if server is up.
        """
        msg = serialize_request(SERVER_STATUS_REQ, [])
        resp = self.send_request(msg)
        return self.parse_response(resp)

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

        taking_off_or_landing skips only the copter altitude limits.
        """
        params = [current_location.to_json(), next_location.to_json()]
        if taking_off_or_landing:
            params.append(True)
        msg = serialize_request(VALIDATE_WAYPOINT_REQ, params)
        resp = self.send_request(msg)
        return self.parse_response(resp)

    def validate_change_speed_command(self, new_speed: float) -> tuple[bool, str]:
        """
        Makes sure the provided new_speed lies within the configured vehicle
        constraints. Returns (False, <error message>) if the speed violates
        constraints, else (True, "").
        """
        msg = serialize_request(VALIDATE_CHANGE_SPEED_REQ, [new_speed])
        resp = self.send_request(msg)
        return self.parse_response(resp)

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
        msg = serialize_request(
            VALIDATE_TAKEOFF_REQ,
            [takeoff_alt, current_lat, current_lon],
        )
        resp = self.send_request(msg)
        return self.parse_response(resp)

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
        msg = serialize_request(VALIDATE_LANDING_REQ, [current_lat, current_lon])
        resp = self.send_request(msg)
        return self.parse_response(resp)

    def validate_velocity_command(
        self,
        current_location: Coordinate,
        velocity: VectorNED,
    ) -> tuple[bool, str]:
        """
        Makes sure a velocity setpoint is within the speed limits and, held
        for a few seconds from current_location, stays inside the geofence.
        Also refused while the vehicle is taken over. Returns (False,
        <error message>) on a violation, else (True, "").
        """
        msg = serialize_request(
            VALIDATE_VELOCITY_REQ,
            [current_location.to_json(), velocity.north, velocity.east, velocity.down],
        )
        return self.parse_response(self.send_request(msg))

    def validate_guided_command(self) -> tuple[bool, str]:
        """
        Whether the E-VM may command the vehicle at all. Returns (False,
        <reason>) while the C-VM filter reports the vehicle taken over (the
        reason starts with TAKEN_OVER_MESSAGE), else (True, "").
        """
        return self.parse_response(self.send_request(serialize_request(VALIDATE_GUIDED_COMMAND_REQ, [])))

    def report_takeoff_location(self, lat: float | None, lon: float | None) -> tuple[bool, str]:
        """
        Set the landing pad validate_landing_command checks against, or clear
        it with None. For the C-VM filter, the authority on the pad.
        """
        resp = self.send_request(serialize_request(REPORT_TAKEOFF_LOCATION_REQ, [lat, lon]))
        return self.parse_response(resp)

    def report_takeover(self, reason: str | None) -> tuple[bool, str]:
        """
        Record why the vehicle is taken over, or clear it with None. For the
        C-VM filter, the authority on takeovers.
        """
        resp = self.send_request(serialize_request(REPORT_TAKEOVER_REQ, [reason]))
        return self.parse_response(resp)

    def report_filter_abort(self, reason: str | None) -> tuple[bool, str]:
        """
        Record why the C-VM filter is exiting, or clear it with None. For the
        filter, so the E-VM can learn why its MAVLink link was cut.
        """
        resp = self.send_request(serialize_request(REPORT_FILTER_ABORT_REQ, [reason]))
        return self.parse_response(resp)

    def get_filter_status(self) -> dict | None:
        """
        Whether the C-VM filter has aborted, and why: a dict with ``aborted``,
        ``reason`` and ``age_s``, or None if the request failed.
        """
        resp = self.send_request(serialize_request(GET_FILTER_STATUS_REQ, []))
        return resp.get("data") if resp.get("result") else None

    def get_limitations(self) -> dict:
        """
        Read the server's configured vehicle limits.

        Returns:
            dict: vehicle_type, min_speed, max_speed, max_vertical_speed,
            min_alt, min_takeoff_alt and max_alt (the last four are None for
            rovers).

        Raises:
            RuntimeError: If the server does not support the request.
        """
        resp = self.send_request(serialize_request(GET_LIMITATIONS_REQ, []))
        result, message = self.parse_response(resp)
        if not result or "data" not in resp:
            raise RuntimeError(f"Safety checker did not return limitations: {message}")
        return resp["data"]


# Backward-compatible camelCase aliases.
SafetyCheckerClient.sendRequest = SafetyCheckerClient.send_request
SafetyCheckerClient.parseResponse = SafetyCheckerClient.parse_response
SafetyCheckerClient.checkServerStatus = SafetyCheckerClient.check_server_status
SafetyCheckerClient.validateWaypointCommand = SafetyCheckerClient.validate_waypoint_command
SafetyCheckerClient.validateChangeSpeedCommand = SafetyCheckerClient.validate_change_speed_command
SafetyCheckerClient.validateTakeoffCommand = SafetyCheckerClient.validate_takeoff_command
SafetyCheckerClient.validateLandingCommand = SafetyCheckerClient.validate_landing_command
SafetyCheckerClient.getLimitations = SafetyCheckerClient.get_limitations
SafetyCheckerClient.validateVelocityCommand = SafetyCheckerClient.validate_velocity_command
SafetyCheckerClient.validateGuidedCommand = SafetyCheckerClient.validate_guided_command
