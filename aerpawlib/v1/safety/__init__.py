"""
safety module
Provides a safety server and client for validating vehicle commands
Unchanged from legacy except to provide aliases for new method names
to maintain backward compatibility with existing code.

@author: John Kesler (morzack)
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
