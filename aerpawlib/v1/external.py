"""
External process utilities for v1 scripts.

This module provides `ExternalProcess`, an asyncio-friendly helper used by v1
code to spawn and interact with subprocesses such as SITL, proxies, and other
supporting tools.

Capabilities
- Start subprocesses with optional stdin/stdout redirection.
- Read process output and send interactive input.
- Wait for output patterns or process exit conditions.

Usage:
- Use this helper inside runner coroutines when experiments need sidecar
  processes managed from mission code.

Notes:
- When streams are redirected to files, interactive helpers may no-op or raise
  a runtime error as documented on each method.
"""

import asyncio
import re
from typing import List, Optional, Pattern, Union


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
        params: Optional[List[str]] = None,
        stdin: Optional[str] = None,
        stdout: Optional[str] = None,
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
        self.process: Optional[asyncio.subprocess.Process] = None

    async def aclose(self) -> None:
        """Reap the subprocess and close streams.

        Avoids PytestUnraisableExceptionWarning from deferred ``BaseSubprocessTransport``
        cleanup after the asyncio loop is closed.
        """
        proc = self.process
        if proc is None:
            return
        try:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
        except ProcessLookupError:
            pass
        for name in ("stdout", "stderr"):
            stream = getattr(proc, name, None)
            if stream is not None:
                try:
                    await stream.read()
                except (
                    BrokenPipeError,
                    ConnectionResetError,
                    ValueError,
                    OSError,
                ):
                    pass
        if proc.stdin is not None:
            try:
                proc.stdin.close()
                await proc.stdin.wait_closed()
            except (
                BrokenPipeError,
                ConnectionResetError,
                ValueError,
                OSError,
                AttributeError,
            ):
                pass

    async def start(self) -> None:
        """
        Start the executable in an asynchronous process.
        """
        executable = self._executable
        executable += " " + " ".join(self._params)
        if not self._stdin is None:
            executable += f" < {self._stdin}"
        if not self._stdout is None:
            executable += f" > {self._stdout}"

        self.process = await asyncio.create_subprocess_shell(
            executable,
            stdout=(None if self._stdout is not None else asyncio.subprocess.PIPE),
            stdin=None if self._stdin is not None else asyncio.subprocess.PIPE,
        )

    async def read_line(self) -> Optional[str]:
        """
        Read one line from the stdout buffer.

        Returns:
            str: The read line decoded to ASCII, or None if the process has stopped
                or stdout is redirected to a file.
        """
        if not self.process.stdout:
            return None
        out = await self.process.stdout.readline()
        if not out:
            return None
        return out.decode("ascii").rstrip()

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
                "Cannot send input: stdin is not available "
                "(was it redirected to a file?)"
            )
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

    async def wait_until_terminated(self) -> None:
        """
        Wait until the process is complete.
        """
        await self.process.wait()

    async def wait_until_output(
        self, output_regex: Union[str, Pattern[str]]
    ) -> List[str]:
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
