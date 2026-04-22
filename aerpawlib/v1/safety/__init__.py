"""
Safety checker package for the v1 API.

This package exposes the client/server components used to validate mission
commands against configured geofences and vehicle constraints.

Capabilities:
- Re-export `SafetyCheckerServer` for ZMQ-based request validation.
- Re-export `SafetyCheckerClient` for vehicle-side safety requests.
- Re-export wire-format helpers for serialized request/response payloads.

Usage:
- Import safety symbols from `aerpawlib.v1.safety` in runners, vehicles, and
  supporting tooling.
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
