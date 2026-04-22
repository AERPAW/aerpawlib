"""
Compressed wire-format helpers for v1 safety messaging.

This module provides utility functions for encoding and decoding safety checker
request/response payloads as compressed JSON blobs.

Capabilities:
- Serialize request and response dictionaries to zlib-compressed bytes.
- Deserialize compressed payloads back into parsed JSON dictionaries.
- Keep on-the-wire payloads compact while preserving debuggable structure.

Usage:
- Used by `SafetyCheckerClient` and `SafetyCheckerServer` for all ZMQ message
  exchange.
"""

import json
import zlib
from typing import Dict


def serialize_msg(raw_json: str) -> bytes:
    """
    Compress JSON message using zlib.

    Args:
        raw_json: The JSON string to compress.

    Returns:
        bytes: Compressed data.
    """
    compressed_msg = zlib.compress(raw_json.encode("utf-8"))
    return compressed_msg


def serialize_request(request_function: str, params: list) -> bytes:
    """
    Serialize a safety checker request into a compressed JSON format.

    Args:
        request_function: The name of the function to request on the server.
        params: List of parameters for the request function.

    Returns:
        bytes: Compressed byte string of the serialized JSON.
    """
    raw_msg = json.dumps(
        {
            "request_function": request_function,
            "params": params,
        }
    )
    return serialize_msg(raw_msg)


def serialize_response(request_function: str, result: bool, message: str = "") -> bytes:
    """
    Serialize a safety checker response into a compressed JSON format.

    Args:
        request_function: The name of the function that was requested.
        result: Whether the request was successful/valid.
        message: Additional information or error reason. Defaults to "".

    Returns:
        bytes: Compressed byte string of the serialized JSON.
    """
    raw_msg = json.dumps(
        {
            "request_function": request_function,
            "result": result,
            "message": message,
        }
    )
    return serialize_msg(raw_msg)


def deserialize_msg(compressed_msg: bytes) -> Dict:
    """
    Decompress and parse a JSON message using zlib.

    Args:
        compressed_msg: The compressed data to decompress.

    Returns:
        dict: The parsed JSON message as a dictionary.
    """
    try:
        raw_msg = zlib.decompress(compressed_msg).decode("utf-8")
        msg = json.loads(raw_msg)
    except zlib.error as e:
        raise ValueError(f"Failed to decompress message: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse message JSON: {e}") from e
    return msg
