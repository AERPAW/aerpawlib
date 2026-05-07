"""
.. include:: ../../docs/v2/aerpaw.md
"""

from __future__ import annotations

import base64
from enum import Enum

import aiohttp
import requests

from .constants import (
    AERPAW_CHECKPOINT_TIMEOUT_S,
    AERPAW_OEO_MSG_TIMEOUT_S,
    AERPAW_PING_TIMEOUT_S,
    DEFAULT_FORWARD_SERVER_IP,
    DEFAULT_FORWARD_SERVER_PORT,
)
from .log import LogComponent, get_logger

logger = get_logger(LogComponent.AERPAW)


class OeoSeverity(str, Enum):
    """Enumeration for OEO message severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AerpawPlatform:
    """
    AERPAW interface for v2.
    Supports OEO logging, checkpoint operations, and user topic publishing.
    """

    def __init__(
        self,
        forward_ip: str = DEFAULT_FORWARD_SERVER_IP,
        forward_port: int = DEFAULT_FORWARD_SERVER_PORT,
        suppress_stdout: bool = False,
    ) -> None:
        self.forward_ip = forward_ip
        self.forward_port = forward_port
        self.suppress_stdout = suppress_stdout

        # Determine connection status upon initialization
        self.is_connected = self._check_connection()

    def _check_connection(self) -> bool:
        """Attempt to connect to the AERPAW forward server."""
        try:
            requests.post(
                f"http://{self.forward_ip}:{self.forward_port}/ping",
                timeout=AERPAW_PING_TIMEOUT_S,
            )
            logger.info(
                f"AERPAW platform: connected to forward server "
                f"{self.forward_ip}:{self.forward_port}"
            )
            return True
        except requests.exceptions.RequestException as e:
            logger.debug(
                f"AERPAW platform: not in AERPAW environment "
                f"({self.forward_ip}:{self.forward_port} unreachable: {e})"
            )
            return False

    def _log_local(self, msg: str, severity: OeoSeverity) -> None:
        """Emit message to the local logger."""
        if self.suppress_stdout:
            return

        # Dynamically map the Enum to the correct logging function
        log_methods = {
            OeoSeverity.INFO: logger.info,
            OeoSeverity.WARNING: logger.warning,
            OeoSeverity.ERROR: logger.error,
            OeoSeverity.CRITICAL: logger.critical,
        }

        log_method = log_methods.get(severity, logger.info)
        log_method(msg)

    def _build_oeo_url(
        self, msg: str, severity: OeoSeverity, agent_id: str | None
    ) -> str:
        """Build the HTTP URL for publishing messages to the OEO forward server."""
        encoded = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("utf-8")
        url = (
            f"http://{self.forward_ip}:{self.forward_port}"
            f"/oeo_msg/{severity.value}/{encoded}"
        )
        if agent_id:
            url += f"/{agent_id}"
        return url

    def _checkpoint_build_request(self, var_type: str, var_name: str) -> str:
        """Build a checkpoint endpoint URL."""
        return (
            f"http://{self.forward_ip}:{self.forward_port}"
            f"/checkpoint/{var_type}/{var_name}"
        )

    def _display_connection_warning(self) -> None:
        """Log a one-time warning when platform-only features are used offline."""
        if not self.suppress_stdout:
            logger.info(
                "the user script has attempted to use AERPAW platform functionality "
                "without being in the AERPAW environment"
            )

    # OEO Logging Methods

    def log_to_oeo(
        self,
        msg: str,
        severity: OeoSeverity = OeoSeverity.INFO,
        agent_id: str | None = None,
    ) -> None:
        """Send a message to the OEO console synchronously."""
        self._log_local(msg, severity)

        if not self.is_connected:
            self._display_connection_warning()
            return

        try:
            requests.post(
                self._build_oeo_url(msg, severity, agent_id),
                timeout=AERPAW_OEO_MSG_TIMEOUT_S,
            )
        except requests.exceptions.RequestException as e:
            if not self.suppress_stdout:
                logger.error(f"Failed to send message to OEO: {e}")

    async def log_to_oeo_async(
        self,
        msg: str,
        severity: OeoSeverity = OeoSeverity.INFO,
        agent_id: str | None = None,
    ) -> None:
        """Send a message to the OEO console asynchronously."""
        self._log_local(msg, severity)

        if not self.is_connected:
            self._display_connection_warning()
            return

        url = self._build_oeo_url(msg, severity, agent_id)
        timeout = aiohttp.ClientTimeout(total=AERPAW_OEO_MSG_TIMEOUT_S)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url):
                    pass
        except aiohttp.ClientError as e:
            if not self.suppress_stdout:
                logger.error(f"Failed to send message to OEO: {e}")

    # Checkpoint Methods

    def checkpoint_reset_server(self) -> None:
        """
        Reset the AERPAW checkpoint server.

        Behavior:
        - Clears checkpoint state from prior experiment runs.
        - Requires an active AERPAW platform connection.

        Raises:
            Exception: If not connected or if the reset request fails.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.post(
            f"http://{self.forward_ip}:{self.forward_port}/checkpoint/reset",
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when resetting checkpoint server")

    def checkpoint_set(self, checkpoint_name: str) -> None:
        """
        Set a boolean checkpoint to `True`.

        Behavior:
        - Creates the checkpoint if it does not already exist.
        - Requires an active AERPAW platform connection.

        Args:
            checkpoint_name: Name of the checkpoint.

        Raises:
            Exception: If not connected or if the update request fails.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.post(
            self._checkpoint_build_request("bool", checkpoint_name),
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when posting to checkpoint server")

    def checkpoint_check(self, checkpoint_name: str) -> bool:
        """
        Read a boolean checkpoint value.

        Args:
            checkpoint_name: Name of the checkpoint.

        Returns:
            `True` when the checkpoint is set, otherwise `False`.

        Raises:
            Exception: If not connected, if the request fails, or if the
                response content is malformed.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.get(
            self._checkpoint_build_request("bool", checkpoint_name),
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when getting from checkpoint server")
        response_content = response.content.decode()
        if response_content == "True":
            return True
        if response_content == "False":
            return False
        raise Exception(
            f"malformed content in response from server: {response_content}"
        )

    def checkpoint_increment_counter(self, counter_name: str) -> None:
        """
        Increment an integer counter.

        Behavior:
        - Increments the named counter by one.
        - Creates the counter at `1` when it does not exist.
        - Requires an active AERPAW platform connection.

        Args:
            counter_name: Name of the counter.

        Raises:
            Exception: If not connected or if the update request fails.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.post(
            self._checkpoint_build_request("int", counter_name),
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when posting to checkpoint server")

    def checkpoint_check_counter(self, counter_name: str) -> int:
        """
        Read the current value of an integer counter.

        Args:
            counter_name: Name of the counter.

        Returns:
            Current value of the counter.

        Raises:
            Exception: If not connected, if the request fails, or if the
                response content is not an integer.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.get(
            self._checkpoint_build_request("int", counter_name),
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when getting from checkpoint server")
        response_content = response.content.decode()
        try:
            return int(response_content)
        except (TypeError, ValueError):
            raise Exception(
                f"malformed content in response from server: {response_content}"
            )

    def checkpoint_set_string(self, string_name: str, value: str) -> None:
        """
        Store a string value in the checkpoint system.

        Behavior:
        - Writes `value` under the checkpoint key `string_name`.
        - Requires an active AERPAW platform connection.

        Args:
            string_name: Key/name for the stored string.
            value: String value to store.

        Raises:
            Exception: If not connected or if the update request fails.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.post(
            self._checkpoint_build_request("string", string_name),
            params={"val": value},
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when posting to checkpoint server")

    def checkpoint_check_string(self, string_name: str) -> str:
        """
        Read a string value from the checkpoint system.

        Args:
            string_name: Key/name for the stored string.

        Returns:
            Stored string value for `string_name`.

        Raises:
            Exception: If not connected or if the request fails.
        """
        if not self.is_connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment"
            )
        response = requests.get(
            self._checkpoint_build_request("string", string_name),
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when getting from checkpoint server")
        return response.content.decode()

    # User Topic Publishing

    def publish_user_oeo_topic(
        self,
        value: str,
        topic: str,
        agent_id: str | None = None,
    ) -> bool:
        """
        Publish a value to a custom OEO user topic.

        Behavior:
        - Base64-encodes `topic`, `value`, and optional `agent_id`.
        - Sends the payload through the forward server when connected.
        - Returns `False` on connection or request failures.

        Args:
            value: Value payload to publish.
            topic: Topic path (for example, `radio/snr`).
            agent_id: Optional message source identifier.

        Returns:
            `True` if the publish request succeeds, otherwise `False`.
        """
        if not self.is_connected:
            self._display_connection_warning()
            return False

        value_b64 = base64.urlsafe_b64encode(str(value).encode("utf-8")).decode("utf-8")
        topic_b64 = base64.urlsafe_b64encode(str(topic).encode("utf-8")).decode("utf-8")

        try:
            if not agent_id:
                requests.post(
                    f"http://{self.forward_ip}:{self.forward_port}"
                    f"/oeo_pub/{topic_b64}/{value_b64}",
                    timeout=AERPAW_OEO_MSG_TIMEOUT_S,
                )
            else:
                agent_b64 = base64.urlsafe_b64encode(
                    str(agent_id).encode("utf-8")
                ).decode("utf-8")
                requests.post(
                    f"http://{self.forward_ip}:{self.forward_port}"
                    f"/oeo_pub/{topic_b64}/{value_b64}/{agent_b64}",
                    timeout=AERPAW_OEO_MSG_TIMEOUT_S,
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"unable to publish value to OEO system. exception: {e}")
            return False
        return True

    async def publish_user_oeo_topic_async(
        self,
        value: str,
        topic: str,
        agent_id: str | None = None,
    ) -> bool:
        """
        Publish a value to a custom OEO user topic asynchronously.

        Behavior:
        - Base64-encodes `topic`, `value`, and optional `agent_id`.
        - Sends the payload through the forward server when connected.
        - Returns `False` on connection or request failures.

        Args:
            value: Value payload to publish.
            topic: Topic path (for example, `radio/snr`).
            agent_id: Optional message source identifier.

        Returns:
            `True` if the publish request succeeds, otherwise `False`.
        """
        if not self.is_connected:
            self._display_connection_warning()
            return False

        value_b64 = base64.urlsafe_b64encode(str(value).encode("utf-8")).decode("utf-8")
        topic_b64 = base64.urlsafe_b64encode(str(topic).encode("utf-8")).decode("utf-8")

        timeout = aiohttp.ClientTimeout(total=AERPAW_OEO_MSG_TIMEOUT_S)

        try:
            if not agent_id:
                url = (
                    f"http://{self.forward_ip}:{self.forward_port}"
                    f"/oeo_pub/{topic_b64}/{value_b64}"
                )
            else:
                agent_b64 = base64.urlsafe_b64encode(
                    str(agent_id).encode("utf-8")
                ).decode("utf-8")
                url = (
                    f"http://{self.forward_ip}:{self.forward_port}"
                    f"/oeo_pub/{topic_b64}/{value_b64}/{agent_b64}"
                )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url):
                    pass
        except aiohttp.ClientError as e:
            logger.error(f"unable to publish value to OEO system. exception: {e}")
            return False
        return True
