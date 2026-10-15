"""
.. include:: ../../docs/v2/external.md
"""

from __future__ import annotations

import asyncio
import contextlib
import re

from aerpawlib._internal.subprocess_io import (
    drain_stream,
    pop_buffered_line,
    reap_process,
)


class ExternalProcess:
    """
    Representation of an external process.

    Async interface for stdin/stdout interaction.
    """

    def __init__(
        self,
        executable: str,
        params: list[str] | None = None,
        stdin: str | None = None,
        stdout: str | None = None,
    ) -> None:
        self._executable = executable
        self._params = params or []
        self._stdin = stdin
        self._stdout = stdout
        self.process: asyncio.subprocess.Process | None = None
        # stdout read while waiting for exit, served to later read_line calls.
        self._stdout_buffer = bytearray()
        self._stdout_lock: asyncio.Lock | None = None

    def _get_stdout_lock(self) -> asyncio.Lock:
        if self._stdout_lock is None:
            self._stdout_lock = asyncio.Lock()
        return self._stdout_lock

    async def aclose(self) -> None:
        """Terminate (then kill) the subprocess with bounded waits, draining stdout."""
        if self.process is None:
            return
        await reap_process(self.process)

    async def start(self) -> None:
        """Start the process."""
        cmd = [self._executable, *self._params]
        # A file name redirects that stream to the file; otherwise it is piped.
        # The child keeps its own copies of the descriptors, so close ours after spawn.
        with contextlib.ExitStack() as files:
            stdin = files.enter_context(open(self._stdin, "rb")) if self._stdin is not None else asyncio.subprocess.PIPE
            stdout = files.enter_context(open(self._stdout, "wb")) if self._stdout is not None else asyncio.subprocess.PIPE
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=stdin,
                stdout=stdout,
            )

    async def read_line(self) -> str | None:
        """Read one line from stdout."""
        if self.process is None or self.process.stdout is None:
            return None
        async with self._get_stdout_lock():
            if self._stdout_buffer:
                line = pop_buffered_line(self._stdout_buffer)
            else:
                line = await self.process.stdout.readline()
        if not line:
            return None
        return line.decode("utf-8", errors="replace").rstrip()

    async def send_input(self, data: str) -> None:
        """Send a string to the process's stdin.

        Args:
            data: The data to send.

        Raises:
            RuntimeError: If stdin is not available (e.g. redirected to a file).
        """
        if self.process is None or self.process.stdin is None:
            raise RuntimeError(
                "Cannot send input: stdin is not available (was it redirected to a file?)",
            )
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

    async def wait_until_terminated(self) -> None:
        """Wait until the process exits.

        Piped stdout is read while waiting (and kept for later ``read_line``
        calls, up to a limit) so a child that writes more than the pipe
        buffer cannot block forever, and ``kill()`` unblocks this call.
        """
        if self.process is None:
            return
        if self.process.stdout is not None:
            async with self._get_stdout_lock():
                await drain_stream(self.process.stdout, self._stdout_buffer)
        await self.process.wait()

    async def wait_until_output(self, output_regex: str) -> list[str]:
        """Block until a stdout line matches the given regex.

        Args:
            output_regex: Regular expression to search for in each output line.

        Returns:
            All lines read up to and including the matching line, or all lines
            collected if the process ends before a match is found.
        """
        buff: list[str] = []
        while True:
            out = await self.read_line()
            if out is None:
                return buff
            buff.append(out)
            if re.search(output_regex, out):
                return buff
