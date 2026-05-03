"""
.. include:: ../../docs/v1/aerpaw.md
"""

import base64
import threading
from typing import Any

import requests

from aerpawlib.v1.log import LogComponent, get_logger

logger = get_logger(LogComponent.AERPAW)
oeo_logger = get_logger(LogComponent.OEO)

from .constants import (  # noqa: E402
    AERPAW_CHECKPOINT_TIMEOUT_S,
    AERPAW_OEO_MSG_TIMEOUT_S,
    AERPAW_PING_TIMEOUT_S,
    DEFAULT_FORWARD_SERVER_IP,
    DEFAULT_FORWARD_SERVER_PORT,
    DEFAULT_HUMAN_READABLE_AGENT_ID,
    OEO_MSG_SEV_CRIT,
    OEO_MSG_SEV_ERR,
    OEO_MSG_SEV_INFO,
    OEO_MSG_SEV_WARN,
    OEO_MSG_SEVS,
)


class AERPAW:
    """
    Client for AERPAW platform services used by v1 scripts.

    Capabilities:
    - Send human-readable messages to the OEO console.
    - Publish custom values to OEO user topics.
    - Set/check checkpoint booleans, counters, and string values.

    Notes:
    - Methods that require platform services either no-op/return safely or
      raise informative exceptions when running outside AERPAW.
    - This class is consumed by CLI internals; use `AERPAW_Platform` instead of
      constructing instances directly.
    """

    _forw_addr: str
    _forw_port: int
    _connected: bool

    _connection_warning_displayed = False

    def __init__(
        self,
        forw_addr: str = DEFAULT_FORWARD_SERVER_IP,
        forw_port: int = DEFAULT_FORWARD_SERVER_PORT,
    ) -> None:
        """
        Initialize the platform client and probe connectivity.

        Args:
            forw_addr: IP or hostname of the AERPAW forward server.
            forw_port: Port of the AERPAW forward server.
        """
        self._forw_addr = forw_addr
        self._forw_port = forw_port
        self._connected = self.attach_to_aerpaw_platform()
        self._no_stdout = False

    def attach_to_aerpaw_platform(self) -> bool:
        """
        Attempt to detect whether the AERPAW platform is reachable.

        Behavior:
        - Sends a ping request to the forward server.
        - Treats request failures as "not connected".

        Returns:
            `True` when the ping request succeeds, otherwise `False`.
        """
        try:
            requests.post(
                f"http://{self._forw_addr}:{self._forw_port}/ping", # noqa
                timeout=AERPAW_PING_TIMEOUT_S,
            )
        except requests.exceptions.RequestException:
            return False
        return True

    def _is_aerpaw_environment(self) -> bool:
        """
        Report whether platform connectivity has been established.

        Returns:
            `True` when connected to AERPAW services, otherwise `False`.
        """
        return self._connected

    def _display_connection_warning(self) -> None:
        """
        Log a one-time warning when platform-only features are used offline.

        Notes:
        - Logging is skipped when stdout mirroring is disabled.
        - The warning is emitted at most once per process.
        """
        if self._connection_warning_displayed:
            return
        if not self._no_stdout:
            logger.info(
                "the user script has attempted to use AERPAW platform functionality "
                "without being in the AERPAW environment",
            )
        self._connection_warning_displayed = True

    def log_to_oeo(
        self,
        msg: str,
        severity: str = OEO_MSG_SEV_INFO,
        agent_id: str = DEFAULT_HUMAN_READABLE_AGENT_ID,
    ) -> None:
        """
        Send a message to the OEO console.

        Behavior:
        - Always mirrors the message to local logs unless `_no_stdout` is set.
        - When connected, submits the message to the forward server.
        - When disconnected, emits a one-time warning and returns.

        Args:
            msg: Human-readable message body.
            severity: Severity label (`info`, `warn`, `error`, or `crit`).
            agent_id: Optional message source identifier.

        Raises:
            Exception: If `severity` is not one of the supported values.
        """
        if not self._no_stdout:
            if severity == OEO_MSG_SEV_INFO:
                oeo_logger.info(msg)
            elif severity == OEO_MSG_SEV_WARN:
                oeo_logger.warning(msg)
            elif severity == OEO_MSG_SEV_ERR:
                oeo_logger.error(msg)
            elif severity == OEO_MSG_SEV_CRIT:
                oeo_logger.critical(msg)
            else:
                oeo_logger.info(msg)

        if not self._connected:
            self._display_connection_warning()
            return

        if severity not in OEO_MSG_SEVS:
            raise Exception("severity provided for log_to_oeo not supported")
        encoded = base64.urlsafe_b64encode(msg.encode("utf-8"))
        try:
            if agent_id:
                requests.post(
                    f"http://{self._forw_addr}:{self._forw_port}" # noqa
                    f"/oeo_msg/{severity}/{encoded.decode('utf-8')}/{agent_id}",
                    timeout=AERPAW_OEO_MSG_TIMEOUT_S,
                )
            else:
                requests.post(
                    f"http://{self._forw_addr}:{self._forw_port}" # noqa
                    f"/oeo_msg/{severity}/{encoded.decode('utf-8')}",
                    timeout=AERPAW_OEO_MSG_TIMEOUT_S,
                )
        except requests.exceptions.RequestException:
            if not self._no_stdout:
                logger.error("unable to send previous message to OEO.")

    def _checkpoint_build_request(self, var_type: str, var_name: str) -> str:
        """
        Build a checkpoint endpoint URL.

        Args:
            var_type: Checkpoint value kind (`bool`, `int`, or `string`).
            var_name: Name/key of the checkpoint value.

        Returns:
            Full HTTP URL for the checkpoint request.
        """
        return (f"http://{self._forw_addr}:{self._forw_port}" # noqa
                f"/checkpoint/{var_type}/{var_name}")

    def checkpoint_reset_server(self) -> None:
        """
        Reset the AERPAW checkpoint server.

        Behavior:
        - Clears checkpoint state from prior experiment runs.
        - Requires an active AERPAW platform connection.

        Raises:
            Exception: If not connected or if the reset request fails.
        """
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
            )
        response = requests.post(
            f"http://{self._forw_addr}:{self._forw_port}/checkpoint/reset", # noqa
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
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
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
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
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
            f"malformed content in response from server: {response_content}",
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
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
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
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
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
                f"malformed content in response from server: {response_content}",
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
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
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
        if not self._connected:
            self._display_connection_warning()
            raise Exception(
                "AERPAW checkpoint functionality only works in AERPAW environment",
            )
        response = requests.get(
            self._checkpoint_build_request("string", string_name),
            timeout=AERPAW_CHECKPOINT_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise Exception("error when getting from checkpoint server")
        return response.content.decode()

    def publish_user_oeo_topic(
        self,
        value: str,
        topic: str,
        agent_id: str = DEFAULT_HUMAN_READABLE_AGENT_ID,
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
        if not self._connected:
            self._display_connection_warning()
            return False

        value_b64 = base64.urlsafe_b64encode(str(value).encode("utf-8")).decode("utf-8")
        topic_b64 = base64.urlsafe_b64encode(str(topic).encode("utf-8")).decode("utf-8")
        agent_b64 = None

        if agent_id is not None:
            agent_b64 = base64.urlsafe_b64encode(str(agent_id).encode("utf-8")).decode(
                "utf-8",
            )

        try:
            if not agent_id:
                requests.post(
                    f"http://{self._forw_addr}:{self._forw_port}" # noqa
                    f"/oeo_pub/{topic_b64}/{value_b64}",
                    timeout=AERPAW_OEO_MSG_TIMEOUT_S,
                )
            else:
                requests.post(
                    f"http://{self._forw_addr}:{self._forw_port}" # noqa
                    f"/oeo_pub/{topic_b64}/{value_b64}/{agent_b64}",
                    timeout=AERPAW_OEO_MSG_TIMEOUT_S,
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"unable to publish value to OEO system. exception: {e}")
            return False
        return True


class _AERPAWLazyProxy:
    """
    Lazy proxy for the `AERPAW` singleton.

    Behavior:
    - Defers construction of `AERPAW` until first attribute access.
    - Uses a lock to keep singleton construction thread-safe.

    Notes:
    - Avoids import-time ping delays when running outside AERPAW.
    """

    def __init__(self) -> None:
        """
        Initialize the proxy without constructing the underlying client.

        Behavior:
        - Sets up empty singleton storage.
        - Prepares a lock for thread-safe lazy initialization.
        """
        self.__dict__["_instance"] = None
        self.__dict__["_lock"] = threading.Lock()

    def _get_instance(self) -> AERPAW:
        """
        Create and memoize the underlying `AERPAW` singleton instance.

        Returns:
            Lazily-created shared `AERPAW` instance.
        """
        if self._instance is None:
            with self._lock:
                # Double-check after acquiring lock
                if self._instance is None:
                    self.__dict__["_instance"] = AERPAW()
        return self._instance # noqa: This is because of shenanigans in __init__

    def __getattr__(self, name: str) -> Any:
        """
        Forward attribute lookup to the lazily-created `AERPAW` instance.

        Args:
            name: Attribute name requested on the proxy.

        Returns:
            Attribute value resolved from the underlying singleton instance.
        """
        return getattr(self._get_instance(), name)


AERPAW_Platform = _AERPAWLazyProxy()
