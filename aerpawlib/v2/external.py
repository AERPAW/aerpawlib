"""
.. include:: ../../docs/v2/external.md
"""

from __future__ import annotations

import asyncio
import re


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

    async def start(self) -> None:
        """Start the process."""
        cmd = [self._executable] + self._params
        stdin = asyncio.subprocess.PIPE if self._stdin is None else None
        stdout = asyncio.subprocess.PIPE if self._stdout is None else None
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=stdin,
            stdout=stdout,
        )

    async def read_line(self) -> str | None:
        """Read one line from stdout."""
        if self.process is None or self.process.stdout is None:
            return None
        line = await self.process.stdout.readline()
        if not line:
            return None
        return line.decode("ascii", errors="replace").rstrip()

    async def send_input(self, data: str) -> None:
        """Send a string to the process's stdin.

        Args:
            data: The data to send.

        Raises:
            RuntimeError: If stdin is not available (e.g. redirected to a file).
        """
        if self.process is None or self.process.stdin is None:
            raise RuntimeError(
                "Cannot send input: stdin is not available "
                "(was it redirected to a file?)",
            )
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

    async def wait_until_terminated(self) -> None:
        """Wait until the process exits."""
        if self.process is None:
            return
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
