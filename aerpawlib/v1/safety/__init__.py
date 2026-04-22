"""
.. include:: ../../../docs/v1/safety.md
"""

from .client import SafetyCheckerClient
from .server import SafetyCheckerServer, _polygon_edges, main_cli
from .wire_format import (
    deserialize_msg,
    serialize_msg,
    serialize_request,
    serialize_response,
)

__all__ = [
    "SafetyCheckerClient",
    "SafetyCheckerServer",
    "_polygon_edges",
    "deserialize_msg",
    "serialize_msg",
    "serialize_request",
    "serialize_response",
]


if __name__ == "__main__":
    main_cli()
