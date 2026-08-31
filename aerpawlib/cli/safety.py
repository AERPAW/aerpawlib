"""Resolve SafetyCheckerServer host/port from CLI flags and the AERPAW environment."""

from __future__ import annotations

import os
from collections.abc import Sequence

from aerpawlib.cli.constants import DEFAULT_SAFETY_CHECKER_PORT

DEFAULT_LOCAL_SAFETY_CHECKER_IP = "127.0.0.1"
"""Safety-checker host used outside AERPAW when only a port is given."""

DEFAULT_CVM_SAFETY_CHECKER_IP = "192.168.32.25"
"""Fallback C-VM XV address when ``AP_EXPENV_CVM_<n>_XV`` is unset or NONE."""

AERPAW_NODE_NUM_ENV = "AP_EXPENV_THIS_CONTAINER_EXP_NODE_NUM"
"""This E-VM's 1-based node index; used to pick ``AP_EXPENV_CVM_<n>_XV``."""

AERPAW_CVM_XV_ENV_TEMPLATE = "AP_EXPENV_CVM_{n}_XV"
"""This node's C-VM address on the vehicle net (safety checker + MAVLink)."""

UNDERSCORE_IP_FLAG = "--safety_checker_ip"
UNDERSCORE_PORT_FLAG = "--safety_checker_port"


def aerpaw_safety_checker_ip() -> str:
    """This node's C-VM XV address (safety checker), not the OEO Console.

    Reads ``AP_EXPENV_CVM_${AP_EXPENV_THIS_CONTAINER_EXP_NODE_NUM}_XV``.
    ``AP_EXPENV_OEOCVM_XM`` is the console XM address and must not be used.
    """
    node = os.getenv(AERPAW_NODE_NUM_ENV, "").strip()
    if node:
        raw = os.getenv(AERPAW_CVM_XV_ENV_TEMPLATE.format(n=node), "").strip()
        if raw and raw.upper() != "NONE":
            return raw
    return DEFAULT_CVM_SAFETY_CHECKER_IP


def _flag_value(extra_args: Sequence[str], flag: str) -> str | None:
    """Return the last value for ``flag`` / ``flag=value`` in ``extra_args``."""
    prefix = f"{flag}="
    found: str | None = None
    i = 0
    while i < len(extra_args):
        arg = extra_args[i]
        if arg == flag:
            if i + 1 < len(extra_args) and not extra_args[i + 1].startswith("-"):
                found = extra_args[i + 1]
                i += 2
                continue
            i += 1
            continue
        if arg.startswith(prefix):
            found = arg[len(prefix) :]
        i += 1
    return found


def parse_underscore_safety_flags(
    extra_args: Sequence[str],
) -> tuple[str | None, int | None]:
    """Read helper-style ``--safety_checker_ip`` / ``--safety_checker_port`` extra args."""
    ip = _flag_value(extra_args, UNDERSCORE_IP_FLAG)
    port_raw = _flag_value(extra_args, UNDERSCORE_PORT_FLAG)
    port: int | None = None
    if port_raw is not None:
        try:
            port = int(port_raw)
        except ValueError:
            port = None
    return ip, port


def resolve_safety_checker_target(
    *,
    ip: str | None,
    port: int | None,
    extra_args: Sequence[str] | None = None,
    is_aerpaw: bool,
) -> tuple[str, int] | None:
    """Return ``(host, port)`` when a library-level client should attach.

    Known dashed flags (``--safety-checker-ip`` / ``--safety-checker-port``) win.
    Unmatched helper extra args (``--safety_checker_ip`` / ``--safety_checker_port``)
    are copied onto the client and still passed through to the script.

    In AERPAW the default host is the C-VM, not localhost. Outside AERPAW, omit
    both flags to skip the client; a port or IP alone still attaches (localhost
    if the IP is omitted).
    """
    extra_ip, extra_port = parse_underscore_safety_flags(extra_args or [])
    resolved_ip = ip if ip is not None else extra_ip
    resolved_port = port if port is not None else extra_port
    if resolved_ip is None and resolved_port is None and not is_aerpaw:
        return None
    if resolved_ip is not None:
        host = resolved_ip
    elif is_aerpaw:
        host = aerpaw_safety_checker_ip()
    else:
        host = DEFAULT_LOCAL_SAFETY_CHECKER_IP
    effective_port = resolved_port if resolved_port is not None else DEFAULT_SAFETY_CHECKER_PORT
    return host, effective_port
