"""
External process utilities for aerpawlib v2.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional


class ExternalProcess:
    """
    Representation of an external process.

    Async interface for stdin/stdout interaction.
    """

    def __init__(
        self,
        executable: str,
        params: Optional[List[str]] = None,
        stdin: Optional[str] = None,
        stdout: Optional[str] = None,
    ) -> None:
        self._executable = executable
        self._params = params or []
        self._stdin = stdin
        self._stdout = stdout
        self.process: Optional[asyncio.subprocess.Process] = None

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

    async def read_line(self) -> Optional[str]:
        """Read one line from stdout."""
        if self.process is None or self.process.stdout is None:
            return None
        line = await self.process.stdout.readline()
        if not line:
            return None
        return line.decode("ascii", errors="replace").rstrip()
