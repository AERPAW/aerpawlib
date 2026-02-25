"""
Logging for aerpawlib v2 API.

Wraps aerpawlib.log with v2-specific component names.
"""

from __future__ import annotations

from typing import Union

from aerpawlib.log import (
    LogLevel,
    configure_logging,
    get_logger as _get_logger,
)


class LogComponent:
    """v2 logging components."""

    ROOT = "aerpawlib.v2"
    VEHICLE = "aerpawlib.v2.vehicle"
    DRONE = "aerpawlib.v2.vehicle.drone"
    ROVER = "aerpawlib.v2.vehicle.rover"
    SAFETY = "aerpawlib.v2.safety"
    RUNNER = "aerpawlib.v2.runner"
    AERPAW = "aerpawlib.v2.aerpaw"
    ZMQ = "aerpawlib.v2.zmq"


def get_logger(component: Union[LogComponent, str] = LogComponent.ROOT):
    """Get logger for v2 component."""
    name = component if isinstance(component, str) else component.value
    return _get_logger(name)


__all__ = ["LogComponent", "get_logger", "configure_logging", "LogLevel"]
