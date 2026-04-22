"""
.. include:: ../../docs/v2/aerpaw.md
"""

from __future__ import annotations

import base64
from typing import Optional

import aiohttp
import requests

from .constants import (
    AERPAW_NOTIFY_TIMEOUT_S,
    AERPAW_PING_TIMEOUT_S,
    DEFAULT_FORWARD_SERVER_IP,
    DEFAULT_FORWARD_SERVER_PORT,
)
from .log import LogComponent, get_logger

logger = get_logger(LogComponent.AERPAW)

OEO_MSG_SEV_INFO = "INFO"
OEO_MSG_SEV_WARN = "WARNING"
OEO_MSG_SEV_ERR = "ERROR"
OEO_MSG_SEV_CRIT = "CRITICAL"


class AERPAW_Platform:
    """
    Minimal AERPAW interface for v2.

    Used for disconnect and critical notifications.
    """

    _instance: Optional["AERPAW_Platform"] = None
    _forw_addr: str = DEFAULT_FORWARD_SERVER_IP
    _forw_port: int = DEFAULT_FORWARD_SERVER_PORT
    _connected: bool = False
    _no_stdout: bool = False

    def __new__(cls) -> "AERPAW_Platform":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized") or not self._initialized:
            self._connected = self._attach()
            self._initialized = True

    def _attach(self) -> bool:
        """Attempt to connect to the AERPAW forward server.

        Returns:
            True if the forward server responded, False otherwise.
        """
        try:
            requests.post(
                f"http://{self._forw_addr}:{self._forw_port}/ping",
                timeout=AERPAW_PING_TIMEOUT_S,
            )
            logger.info(
                f"AERPAW platform: connected to forward server {self._forw_addr}:{self._forw_port}"
            )
            return True
        except requests.exceptions.RequestException as e:
            logger.debug(
                f"AERPAW platform: not in AERPAW environment ({self._forw_addr}:{self._forw_port} unreachable: {e})"
            )
            return False

    def _is_aerpaw_environment(self) -> bool:
        """Return True if the AERPAW forward server is reachable."""
        return self._connected

    def set_no_stdout(self, value: bool) -> None:
        """Suppress stdout logging when True.

        Args:
            value: If True, log messages are not printed to stdout.
        """
        self._no_stdout = value

    def _log_to_oeo_local(self, msg: str, severity: str) -> None:
        """Emit *msg* to the local logger according to *severity*."""
        if self._no_stdout:
            return
        if severity == OEO_MSG_SEV_CRIT:
            logger.critical(msg)
        elif severity == OEO_MSG_SEV_ERR:
            logger.error(msg)
        elif severity == OEO_MSG_SEV_WARN:
            logger.warning(msg)
        else:
            logger.info(msg)

    def _oeo_message_url(self, msg: str, severity: str, agent_id: Optional[str]) -> str:
        """Build the HTTP URL for publishing *msg* to the OEO forward server."""
        encoded = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("utf-8")
        url = f"http://{self._forw_addr}:{self._forw_port}/oeo_msg/{severity}/{encoded}"
        if agent_id:
            url += f"/{agent_id}"
        return url

    def log_to_oeo(
        self,
        msg: str,
        severity: str = OEO_MSG_SEV_INFO,
        agent_id: Optional[str] = None,
    ) -> None:
        """Send a message to the OEO console.

        Logs locally according to severity, then forwards to the OEO forward
        server if connected.

        Args:
            msg: Human-readable message to send.
            severity: One of the OEO_MSG_SEV_* constants (INFO, WARNING, ERROR,
                CRITICAL).
            agent_id: Optional agent identifier appended to the request URL.
        """
        self._log_to_oeo_local(msg, severity)
        if not self._connected:
            return
        try:
            requests.post(
                self._oeo_message_url(msg, severity, agent_id),
                timeout=AERPAW_NOTIFY_TIMEOUT_S,
            )
        except requests.exceptions.RequestException as e:
            if not self._no_stdout:
                logger.error(f"Failed to send message to OEO: {e}")

    async def log_to_oeo_async(
        self,
        msg: str,
        severity: str = OEO_MSG_SEV_INFO,
        agent_id: Optional[str] = None,
    ) -> None:
        """Async variant of ``log_to_oeo`` for use from asyncio (non-blocking HTTP)."""
        self._log_to_oeo_local(msg, severity)
        if not self._connected:
            return
        url = self._oeo_message_url(msg, severity, agent_id)
        timeout = aiohttp.ClientTimeout(total=AERPAW_NOTIFY_TIMEOUT_S)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url):
                    pass
        except aiohttp.ClientError as e:
            if not self._no_stdout:
                logger.error(f"Failed to send message to OEO: {e}")
