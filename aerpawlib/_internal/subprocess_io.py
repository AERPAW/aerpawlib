"""Shared stdout draining / reaping for v1 and v2 ``ExternalProcess``.

asyncio stops reading a subprocess pipe once its buffer fills (~64 KiB). The
child then blocks in ``write`` and never exits, and ``Process.wait()`` does
not return while the pipe is paused, even after ``kill()``. Anything that
waits for the child must keep reading its stdout.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
import shutil
import warnings
from pathlib import Path
from typing import Any

logger = logging.getLogger("aerpawlib")

STDOUT_READ_CHUNK_BYTES = 64 * 1024
STDOUT_BUFFER_MAX_BYTES = 1024 * 1024
"""Max stdout bytes kept by ``wait_until_terminated`` for later ``read_line``."""

TERMINATE_TIMEOUT_S = 5.0
"""Seconds ``aclose`` waits after SIGTERM before SIGKILL."""

KILL_TIMEOUT_S = 2.0
"""Seconds ``aclose`` waits after SIGKILL (and for pipes to close)."""


def build_command(executable: str, params: list[str]) -> list[str]:
    """Return the argv for ``create_subprocess_exec`` (never a shell).

    Older v1 releases ran ``executable`` through ``/bin/sh``. To keep the
    ``ExternalProcess("python3 tool.py")`` form working, an executable that is
    not a file or a PATH entry but contains whitespace is split with
    ``shlex`` (no shell expansion, redirection, or command chaining).
    """
    if not shutil.which(executable) and not Path(executable).exists() and any(c.isspace() for c in executable.strip()):
        warnings.warn(
            "ExternalProcess no longer uses a shell; pass the program as executable and its arguments as params",
            DeprecationWarning,
            stacklevel=3,
        )
        return [*shlex.split(executable), *params]
    return [executable, *params]


def pop_buffered_line(buffer: bytearray) -> bytes:
    """Remove and return the first line (including ``\\n``) from ``buffer``."""
    idx = buffer.find(b"\n")
    if idx == -1:
        line = bytes(buffer)
        buffer.clear()
        return line
    line = bytes(buffer[: idx + 1])
    del buffer[: idx + 1]
    return line


async def drain_stream(
    stream: asyncio.StreamReader,
    buffer: bytearray | None = None,
    max_bytes: int = STDOUT_BUFFER_MAX_BYTES,
) -> None:
    """Read ``stream`` to EOF, keeping up to ``max_bytes`` in ``buffer`` (if given)."""
    warned = False
    while True:
        chunk = await stream.read(STDOUT_READ_CHUNK_BYTES)
        if not chunk:
            return
        if buffer is None:
            continue
        room = max_bytes - len(buffer)
        if room > 0:
            buffer.extend(chunk[:room])
        if len(chunk) > room and not warned:
            warned = True
            logger.warning(
                "ExternalProcess stdout exceeded %d buffered bytes while waiting for exit; discarding the rest",
                max_bytes,
            )


def close_pipe_transports(proc: Any) -> None:
    """Close the parent's ends of the child's pipes (stops waiting on them)."""
    transport = getattr(proc, "_transport", None)
    if transport is None:
        return
    for fd in (0, 1, 2):
        with contextlib.suppress(Exception):
            pipe = transport.get_pipe_transport(fd)
            if pipe is not None:
                pipe.close()


async def reap_process(proc: Any) -> None:
    """Terminate (then kill) ``proc`` with bounded waits, draining stdout meanwhile."""
    drain: asyncio.Future | None = None
    if proc.stdout is not None:
        drain = asyncio.ensure_future(drain_stream(proc.stdout))
    try:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=TERMINATE_TIMEOUT_S)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=KILL_TIMEOUT_S)
                except asyncio.TimeoutError:
                    # A grandchild may still hold the pipe; stop waiting on it.
                    close_pipe_transports(proc)
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(proc.wait(), timeout=KILL_TIMEOUT_S)
        if drain is not None:
            try:
                await asyncio.wait_for(asyncio.shield(drain), timeout=KILL_TIMEOUT_S)
            except asyncio.TimeoutError:
                close_pipe_transports(proc)
            except Exception:
                # e.g. another coroutine is already reading stdout.
                pass
    finally:
        if drain is not None and not drain.done():
            drain.cancel()
        if drain is not None:
            await asyncio.gather(drain, return_exceptions=True)
    if proc.stdin is not None:
        try:
            proc.stdin.close()
            await asyncio.wait_for(proc.stdin.wait_closed(), timeout=KILL_TIMEOUT_S)
        except (
            BrokenPipeError,
            ConnectionResetError,
            ValueError,
            OSError,
            AttributeError,
            asyncio.TimeoutError,
        ):
            pass
