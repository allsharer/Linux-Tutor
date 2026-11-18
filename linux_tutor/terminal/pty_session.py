"""A pseudo-terminal session running a host program (normally `podman exec -it ... bash -l`).

This module is UI-independent: it owns the PTY file descriptor and the child process.
The Qt terminal widget (ui/terminal_widget.py) reads from and writes to it; a future
web front end could relay the same file descriptor over a WebSocket.

Student commands are never run on the host: the only host process started here is the
container runtime client, which attaches the PTY to a Bash shell *inside* the lab.
"""
from __future__ import annotations

import errno
import fcntl
import logging
import os
import signal
import struct
import subprocess
import termios

log = logging.getLogger(__name__)


class PtySession:
    def __init__(self, argv: list[str], cols: int = 80, rows: int = 24, env: dict | None = None):
        self.argv = argv
        master, slave = os.openpty()
        self.fd = master
        self._set_winsize(slave, rows, cols)
        child_env = dict(os.environ)
        child_env.update({"TERM": "xterm-256color", "COLUMNS": str(cols), "LINES": str(rows)})
        if env:
            child_env.update(env)

        def _child_setup():  # runs in the child between fork and exec
            os.login_tty(slave)

        self.proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, env=child_env,
                                     preexec_fn=_child_setup, close_fds=True)
        os.close(slave)
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.closed = False

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def resize(self, cols: int, rows: int) -> None:
        if self.closed:
            return
        try:
            self._set_winsize(self.fd, rows, cols)
            os.kill(self.proc.pid, signal.SIGWINCH)
        except OSError:
            pass

    def read(self, size: int = 65536) -> bytes | None:
        """Return available bytes, b'' if nothing is available, or None at end of session."""
        if self.closed:
            return None
        try:
            data = os.read(self.fd, size)
        except BlockingIOError:
            return b""
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                self.close()
                return None
            raise
        if not data:
            self.close()
            return None
        return data

    def write(self, data: bytes) -> None:
        if self.closed:
            return
        view = memoryview(data)
        while view:
            try:
                n = os.write(self.fd, view)
                view = view[n:]
            except BlockingIOError:
                import select
                select.select([], [self.fd], [], 1.0)
            except OSError:
                self.close()
                return

    def alive(self) -> bool:
        return not self.closed and self.proc.poll() is None

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            os.close(self.fd)
        except OSError:
            pass
        if self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
