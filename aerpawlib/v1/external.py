"""
.. include:: ../../docs/v1/external.md
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from re import Pattern

from aerpawlib._internal.subprocess_io import (
    build_command,
    drain_stream,
    pop_buffered_line,
    reap_process,
)


class ExternalProcess:
    """
    Representation of an external process spawned by the script.

    Allows for asynchronous interaction with standard streams (stdin, stdout)
    and dynamic passing of command-line arguments.

    Attributes:
        _executable: Path to the executable.
        _params: List of command-line arguments.
        _stdin: Path to a file to use for stdin redirection.
        _stdout: Path to a file to use for stdout redirection.
        process: The underlying process object.
    """

    def __init__(
        self,
        executable: str,
        params: list[str] | None = None,
        stdin: str | None = None,
        stdout: str | None = None,
    ) -> None:
        """
        Prepare external process for execution.

        Does NOT execute process immediately; call `start()` to run it.

        Args:
            executable: The executable path or command.
            params: Parameters to pass to the process. Defaults to None.
            stdin: Filename for stdin redirection. Defaults to None.
            stdout: Filename for stdout redirection. Defaults to None.
        """
        self._executable = executable
        self._params = params if params is not None else []
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
        """Terminate (then kill) the subprocess and close its streams.

        Waits are bounded, and stdout is drained meanwhile so a child blocked
        on a full pipe can exit. Avoids PytestUnraisableExceptionWarning from
        deferred ``BaseSubprocessTransport`` cleanup after the loop is closed.
        """
        proc = self.process
        if proc is None:
            return
        await reap_process(proc)

    async def start(self) -> None:
        """
        Start the executable in an asynchronous process.

        The program is run directly (no shell). ``params`` are passed as argv
        entries, and ``stdin`` / ``stdout`` file names are opened as files,
        so none of them are interpreted by a shell.
        """
        cmd = build_command(self._executable, self._params)
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
        """
        Read one line from the stdout buffer.

        Returns:
            str: The read line decoded as UTF-8 (invalid bytes replaced), or
                None if the process has stopped or stdout is redirected to a file.
        """
        if self.process is None or not self.process.stdout:
            return None
        async with self._get_stdout_lock():
            if self._stdout_buffer:
                out = pop_buffered_line(self._stdout_buffer)
            else:
                out = await self.process.stdout.readline()
        if not out:
            return None
        return out.decode("utf-8", errors="replace").rstrip()

    async def send_input(self, data: str) -> None:
        """
        Send a string to the process's stdin.

        Args:
            data: The data to send.

        Raises:
            RuntimeError: If stdin is not available (e.g. redirected to a file).
        """
        if self.process.stdin is None:
            raise RuntimeError(
                "Cannot send input: stdin is not available (was it redirected to a file?)",
            )
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

    async def wait_until_terminated(self) -> None:
        """
        Wait until the process is complete.

        Piped stdout is read while waiting (and kept for later ``read_line``
        calls, up to a limit) so a child that writes more than the pipe
        buffer cannot block forever, and ``kill()`` unblocks this call.
        """
        proc = self.process
        if proc is None:
            return
        if proc.stdout is not None:
            async with self._get_stdout_lock():
                await drain_stream(proc.stdout, self._stdout_buffer)
        await proc.wait()

    async def wait_until_output(
        self,
        output_regex: str | Pattern[str],
    ) -> list[str]:
        """
        Block and wait until a line matching the given regex is found in stdout.

        Only works if stdout is not redirected to a file.

        Args:
            output_regex: The regular expression to search for.

        Returns:
            List[str]: All lines read from stdout up to and including the matching line.
                Returns the buffer collected so far if the process ends or stdout
                is unavailable before a match is found.
        """
        buff = []
        while True:
            out = await self.read_line()
            if out is None:
                return buff
            buff.append(out)
            if re.search(output_regex, out):
                return buff
