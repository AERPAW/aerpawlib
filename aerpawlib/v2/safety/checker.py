"""
SafetyCheckerClient for aerpawlib v2.

Async ZMQ client for external geofence validation.
"""

from __future__ import annotations

import json
import zlib
from typing import Tuple

import zmq
import zmq.asyncio
import asyncio

from ..constants import (
    SAFETY_CHECKER_REQUEST_TIMEOUT_S,
    SERVER_STATUS_REQ,
    VALIDATE_WAYPOINT_REQ,
    VALIDATE_CHANGE_SPEED_REQ,
    VALIDATE_TAKEOFF_REQ,
    VALIDATE_LANDING_REQ,
)
from ..log import LogComponent, get_logger
from ..types import Coordinate

logger = get_logger(LogComponent.SAFETY)


def _serialize_request(request_function: str, params: list) -> bytes:
    raw = json.dumps({"request_function": request_function, "params": params})
    return zlib.compress(raw.encode("utf-8"))


def _deserialize_response(data: bytes) -> dict:
    raw = zlib.decompress(data).decode("utf-8")
    return json.loads(raw)


class NoOpSafetyChecker:
    """
    Passthrough safety checker when SafetyCheckerServer is not available.

    All validations return (True, ""). Logs an error explaining that the
    safety checker server is not connected/configured on init and on each validation call.
    """

    def __init__(self, reason: str) -> None:
        """Initialise the no-op checker and log a warning.

        Args:
            reason: Human-readable explanation of why the real checker is
                unavailable (used in the warning log message).
        """
        self._reason = reason
        logger.warning(
            "SafetyCheckerServer not available. All safety validations through SafetyCheckerClient will pass. %s",
            reason,
        )

    async def validate_takeoff(
        self, takeoff_alt: float, current_lat: float, current_lon: float
    ) -> Tuple[bool, str]:
        """Passthrough takeoff validation — always returns True.

        Args:
            takeoff_alt: Requested takeoff altitude in metres.
            current_lat: Current latitude in degrees.
            current_lon: Current longitude in degrees.

        Returns:
            Tuple of (True, "").
        """
        logger.warning("NoOpSafetyChecker: validate_takeoff called but no safety checker server available. Returning true.")
        return True, ""

    async def validate_waypoint(
        self, current: Coordinate, next_loc: Coordinate
    ) -> Tuple[bool, str]:
        """Passthrough waypoint validation — always returns True.

        Args:
            current: Current vehicle position.
            next_loc: Target waypoint coordinate.

        Returns:
            Tuple of (True, "").
        """
        logger.warning("NoOpSafetyChecker: validate_waypoint called but no safety checker server available. Returning true.")
        return True, ""

    async def validate_change_speed(self, new_speed: float) -> Tuple[bool, str]:
        """Passthrough speed validation — always returns True.

        Args:
            new_speed: Requested new speed in m/s.

        Returns:
            Tuple of (True, "").
        """
        logger.warning("NoOpSafetyChecker: validate_change_speed called but no safety checker server available. Returning true.")
        return True, ""

    async def validate_landing(
        self, current_lat: float, current_lon: float
    ) -> Tuple[bool, str]:
        """Passthrough landing validation — always returns True.

        Args:
            current_lat: Current latitude in degrees.
            current_lon: Current longitude in degrees.

        Returns:
            Tuple of (True, "").
        """
        logger.warning("NoOpSafetyChecker: validate_landing called but no safety checker server available. Returning true.")
        return True, ""


class SafetyCheckerClient:
    """Async client for SafetyCheckerServer via ZMQ."""

    def __init__(
        self,
        addr: str,
        port: int,
        timeout_s: float = SAFETY_CHECKER_REQUEST_TIMEOUT_S,
    ) -> None:
        """Connect the ZMQ REQ socket to the safety checker server.

        Args:
            addr: Hostname or IP address of the SafetyCheckerServer.
            port: TCP port the server is listening on.
            timeout_s: Per-request send/receive timeout in seconds.
        """
        self._addr = addr
        self._port = port
        self._timeout_s = timeout_s
        logger.info(f"SafetyCheckerClient: connecting to {addr}:{port} (timeout={timeout_s}s)")
        self._ctx = zmq.asyncio.Context()
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(f"tcp://{addr}:{port}")

    def _reconnect(self) -> None:
        """Recreate the REQ socket after a send/recv error to recover from a stuck state."""
        logger.warning("SafetyCheckerClient: reconnecting socket after error")
        try:
            self._socket.close()
        except Exception:
            pass
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(f"tcp://{self._addr}:{self._port}")

    def close(self) -> None:
        """Close the ZMQ socket and terminate the context."""
        logger.debug("SafetyCheckerClient: closing connection")
        self._socket.close()
        self._ctx.term()

    async def _send_request(self, msg: bytes) -> Tuple[bool, str]:
        """Send a serialised request and await the response.

        Args:
            msg: Compressed request payload produced by _serialize_request.

        Returns:
            Tuple of (result, message) from the server response.

        Raises:
            TimeoutError: If the server does not respond within timeout_s.
        """
        try:
            await asyncio.wait_for(self._socket.send(msg), timeout=self._timeout_s)
            raw = await asyncio.wait_for(self._socket.recv(), timeout=self._timeout_s)
        except asyncio.TimeoutError as e:
            self._reconnect()
            timeout_err = TimeoutError(
                f"SafetyCheckerServer did not respond within {self._timeout_s}s"
            )
            logger.error(f"SafetyCheckerClient: request timed out; socket reset")
            raise timeout_err from e
        except Exception as e:
            self._reconnect()
            logger.error(f"SafetyCheckerClient: request failed ({e}); socket reset")
            raise
        resp = _deserialize_response(raw)
        result, message = resp["result"], resp.get("message", "")
        logger.debug(f"SafetyCheckerClient: response result={result}, message={message}")
        return result, message

    async def check_server_status(self) -> Tuple[bool, str]:
        """Query the server status endpoint.

        Returns:
            Tuple of (ok, message) indicating whether the server is healthy.
        """
        msg = _serialize_request(SERVER_STATUS_REQ, [])
        return await self._send_request(msg)

    async def validate_waypoint(
        self, current: Coordinate, next_loc: Coordinate
    ) -> Tuple[bool, str]:
        """Validate a waypoint navigation command with the server.

        Args:
            current: Current vehicle position.
            next_loc: Target waypoint coordinate.

        Returns:
            Tuple of (ok, message). ok is False if the server rejects the waypoint.
        """
        logger.debug(
            f"SafetyCheckerClient: validate_waypoint current=({current.lat:.6f},{current.lon:.6f}) "
            f"next=({next_loc.lat:.6f},{next_loc.lon:.6f})"
        )
        msg = _serialize_request(
            VALIDATE_WAYPOINT_REQ,
            [current.to_json(), next_loc.to_json()],
        )
        return await self._send_request(msg)

    async def validate_change_speed(self, new_speed: float) -> Tuple[bool, str]:
        """Validate a speed change command with the server.

        Args:
            new_speed: Requested new speed in m/s.

        Returns:
            Tuple of (ok, message). ok is False if the server rejects the speed.
        """
        msg = _serialize_request(VALIDATE_CHANGE_SPEED_REQ, [new_speed])
        return await self._send_request(msg)

    async def validate_takeoff(
        self, takeoff_alt: float, current_lat: float, current_lon: float
    ) -> Tuple[bool, str]:
        """Validate a takeoff command with the server.

        Args:
            takeoff_alt: Requested takeoff altitude in metres.
            current_lat: Current latitude in degrees.
            current_lon: Current longitude in degrees.

        Returns:
            Tuple of (ok, message). ok is False if the server rejects the takeoff.
        """
        msg = _serialize_request(
            VALIDATE_TAKEOFF_REQ, [takeoff_alt, current_lat, current_lon]
        )
        return await self._send_request(msg)

    async def validate_landing(
        self, current_lat: float, current_lon: float
    ) -> Tuple[bool, str]:
        """Validate a landing command with the server.

        Args:
            current_lat: Current latitude in degrees.
            current_lon: Current longitude in degrees.

        Returns:
            Tuple of (ok, message). ok is False if the server rejects the landing.
        """
        msg = _serialize_request(VALIDATE_LANDING_REQ, [current_lat, current_lon])
        return await self._send_request(msg)
