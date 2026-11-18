from __future__ import annotations

import abc
from dataclasses import dataclass, field


class LabError(Exception):
    """The laboratory is unavailable or a lab operation failed."""


@dataclass
class ExecResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class LabStatus:
    engine_available: bool = False
    engine_version: str = ""
    image_present: bool = False
    container_exists: bool = False
    running: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.engine_available and self.image_present and self.running and not self.problems


STUDENT_USER = "student"
STUDENT_HOME = "/home/student"


class LabBackend(abc.ABC):
    """Interface to one isolated laboratory system."""

    student_user = STUDENT_USER
    student_home = STUDENT_HOME

    @abc.abstractmethod
    def status(self) -> LabStatus: ...

    @abc.abstractmethod
    def ensure_running(self, progress=None) -> None:
        """Create and/or start the laboratory, waiting until it is usable."""

    @abc.abstractmethod
    def exec(self, script: str, user: str = "root", timeout: float | None = None,
             stdin: str | None = None) -> ExecResult:
        """Run a bash script inside the laboratory (never on the host)."""

    @abc.abstractmethod
    def shell_argv(self, user: str | None = None) -> list[str]:
        """argv of a host process that attaches an interactive Bash shell to the lab."""

    @abc.abstractmethod
    def reset(self, progress=None) -> None:
        """Destroy the laboratory and recreate it from the pristine image."""

    @abc.abstractmethod
    def stop(self) -> None: ...

    def health_check(self) -> list[str]:
        """Return a list of problems (empty when the laboratory is fully usable)."""
        problems = []
        try:
            r = self.exec("id -un; test -d /home/student && echo HOME_OK; "
                          "ps -p 1 -o comm=; echo ok > /tmp/.tutor-health && cat /tmp/.tutor-health",
                          user=self.student_user, timeout=20)
        except LabError as exc:
            return [f"cannot run commands in the laboratory: {exc}"]
        out = r.stdout.split()
        if not r.ok or "student" not in out:
            problems.append("the student account is not working in the laboratory")
        if "HOME_OK" not in out:
            problems.append("the student home directory is missing")
        if "ok" not in out:
            problems.append("the laboratory filesystem is not writable")
        return problems
