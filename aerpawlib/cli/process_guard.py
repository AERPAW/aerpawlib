"""Keep CLI child processes from outliving a failed or force-killed experiment.

``mavsdk.System`` starts ``mavsdk_server`` and only kills it from ``atexit``
or ``System.__del__``. When ``connect`` fails, the traceback keeps the
``System`` alive, the server's non-daemon log thread keeps the interpreter
alive, and a SIGTERM skips ``atexit``: the server is orphaned holding its gRPC
port. The CLI records every server it spawns so it can kill them on connect
failure and before a forced exit.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("aerpawlib")

MAVSDK_SERVER_KILL_WAIT_S = 2.0
"""Seconds to wait for a killed ``mavsdk_server`` to be reaped."""

_lock = threading.Lock()
_spawned: list[Any] = []
_installed = False
_reject_new = False


def _kill_process(proc: Any) -> bool:
    """Kill one server process. Returns True if it was still running."""
    try:
        if proc.poll() is not None:
            return False
        proc.kill()
    except OSError:
        return False
    try:
        proc.wait(timeout=MAVSDK_SERVER_KILL_WAIT_S)
    except subprocess.TimeoutExpired:
        logger.warning("mavsdk_server pid %s did not exit after kill", getattr(proc, "pid", "?"))
    return True


def install_mavsdk_server_tracking() -> None:
    """Record every ``mavsdk_server`` started through ``mavsdk.System`` (idempotent)."""
    global _installed
    with _lock:
        if _installed:
            return
        try:
            from mavsdk import system as mavsdk_system
        except ImportError:
            return
        original = mavsdk_system.System._start_mavsdk_server

        def _tracked_start(*args: Any, **kwargs: Any) -> Any:
            proc = original(*args, **kwargs)
            with _lock:
                _spawned.append(proc)
                reject = _reject_new
            if reject:
                logger.warning("Killing mavsdk_server started after experiment shutdown")
                _kill_process(proc)
            return proc

        mavsdk_system.System._start_mavsdk_server = staticmethod(_tracked_start)
        _installed = True


def mavsdk_server_mark() -> int:
    """Return a marker for ``kill_mavsdk_servers(since=...)``."""
    with _lock:
        return len(_spawned)


def kill_mavsdk_servers(since: int = 0, *, reject_new: bool = False) -> int:
    """Kill tracked servers spawned at or after ``since``. Returns how many were running.

    With ``reject_new``, any server spawned later (e.g. by a connect thread that
    outlived its timeout) is killed as soon as it starts.
    """
    global _reject_new
    with _lock:
        if reject_new:
            _reject_new = True
        procs = list(_spawned[since:])
    killed = 0
    for proc in procs:
        if _kill_process(proc):
            killed += 1
    if killed:
        logger.info("Stopped %d orphaned mavsdk_server process(es)", killed)
    return killed


class ShutdownSignalHandler:
    """First SIGINT/SIGTERM requests a graceful shutdown; the second forces exit.

    The forced path kills tracked ``mavsdk_server`` children, restores the
    default disposition, and re-raises the signal, so a mission that swallows
    cancellation can still be stopped with a second Ctrl-C.
    """

    def __init__(self, on_first: Callable[[], None]) -> None:
        self._on_first = on_first
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def __call__(self, signum: int, _frame: Any = None) -> None:
        self._count += 1
        if self._count == 1:
            self._on_first()
            return
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        logger.critical("Second %s received; forcing exit without further cleanup", name)
        try:
            kill_mavsdk_servers(reject_new=True)
        except Exception as e:
            logger.debug(f"Failed to stop mavsdk_server before forced exit: {e}")
        force_exit_with_signal(signum)

    def for_signal(self, signum: int) -> Callable[[], None]:
        """Zero-argument callback for ``loop.add_signal_handler``."""
        return lambda: self(signum)


def force_exit_with_signal(signum: int) -> None:
    """Restore the default handler for ``signum`` and deliver it to this process."""
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)
    # Only reached if the default action does not terminate (should not happen
    # for SIGINT/SIGTERM).
    os._exit(128 + signum)
