"""
Implementation of ZMQ utilities for v2.

Implementation lives in ``aerpawlib._internal.zmq`` so v1 and v2 share one
transport. This module re-exports the public helpers used by the v2 runner
and by older tests.
"""

from aerpawlib._internal.zmq import (
    check_zmq_proxy_reachable,
    decode_message,
    encode_message,
    run_zmq_proxy,
)

__all__ = [
    "check_zmq_proxy_reachable",
    "decode_message",
    "encode_message",
    "run_zmq_proxy",
]
