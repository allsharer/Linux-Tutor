"""Rootless Podman implementation of the laboratory.

Isolation model (see SECURITY.md for the full discussion):

* rootless Podman: container "root" is mapped to the invoking host user's
  sub-UID range, so it has no more host privilege than the student's own account;
* no host directories are mounted into the container;
* networking is disabled by default (``--network none``);
* memory, CPU and process-count limits stop runaway programs (fork bombs);
* Podman's default seccomp profile and capability set apply; only the extra
  capabilities needed for curriculum topics (configurable) are added, and they
  are effective only inside the container's own user namespace;
* the lab is disposable: ``reset()`` deletes the container and creates a fresh
  one from the read-only image.  Student records are stored on the host, never
  inside the container, so they are unaffected.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from .. import paths
from . import LAB_IMAGE_VERSION
from .base import ExecResult, LabBackend, LabError, LabStatus

log = logging.getLogger(__name__)

Progress = Callable[[str], None] | None


def _sanitize(name: str) -> str:
    s = re.sub(r"[^a-z0-9_.-]+", "-", name.lower()).strip("-.")
    return s or "default"


def podman_path() -> str | None:
    return shutil.which("podman")


class PodmanLab(LabBackend):
    def __init__(self, config, profile_key: str, kind: str = "lesson"):
        self.config = config
        self.kind = kind
        self.profile_key = _sanitize(profile_key)
        self.name = f"linux-tutor-{kind}-{self.profile_key}"
        self.image = f"{config.get('lab.image')}:{LAB_IMAGE_VERSION}"
        self.timeout = float(config.get("lab.command_timeout", 60))
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ helpers
    def _podman(self, *args: str, timeout: float | None = 120, check: bool = False,
                input: str | None = None) -> subprocess.CompletedProcess:
        exe = podman_path()
        if not exe:
            raise LabError("Podman is not installed. Install it with: sudo apt install podman")
        try:
            cp = subprocess.run([exe, *args], capture_output=True, text=True,
                                timeout=timeout, input=input, errors="replace")
        except subprocess.TimeoutExpired as exc:
            raise LabError(f"podman {args[0]} timed out after {timeout}s") from exc
        if check and cp.returncode != 0:
            raise LabError(f"podman {' '.join(args[:2])} failed: {cp.stderr.strip() or cp.stdout.strip()}")
        return cp

    def _inspect(self) -> dict | None:
        cp = self._podman("container", "inspect", self.name, timeout=30)
        if cp.returncode != 0:
            return None
        try:
            data = json.loads(cp.stdout)
            return data[0] if data else None
        except (json.JSONDecodeError, IndexError):
            return None

    def image_present(self) -> bool:
        return self._podman("image", "exists", self.image, timeout=30).returncode == 0

    # ------------------------------------------------------------------ status
    def status(self) -> LabStatus:
        st = LabStatus()
        if not podman_path():
            st.problems.append("Podman is not installed (sudo apt install podman).")
            return st
        cp = self._podman("version", "--format", "{{.Client.Version}}", timeout=30)
        if cp.returncode != 0:
            st.problems.append(f"Podman does not work for this user: {cp.stderr.strip()}")
            return st
        st.engine_available = True
        st.engine_version = cp.stdout.strip()
        st.image_present = self.image_present()
        info = self._inspect()
        if info:
            st.container_exists = True
            st.running = bool(info.get("State", {}).get("Running"))
            if info.get("ImageName") and info.get("ImageName") != self.image:
                st.problems.append("The laboratory was created from an older image; reset it to upgrade.")
        if not st.image_present:
            st.problems.append("The laboratory image has not been built or imported yet.")
        return st

    # ------------------------------------------------------------------ lifecycle
    def _run_args(self, with_limits: bool = True) -> list[str]:
        cfg = self.config
        args = ["run", "-d", "--name", self.name, "--hostname", "linuxlab",
                "--label", "org.linuxtutor.managed=true",
                "--label", f"org.linuxtutor.profile={self.profile_key}",
                "--label", f"org.linuxtutor.kind={self.kind}",
                "--stop-timeout", "5",
                "--network", cfg.get("lab.network", "none") or "none"]
        if with_limits:
            args += ["--memory", str(cfg.get("lab.memory", "1g")),
                     "--cpus", str(cfg.get("lab.cpus", "1.5")),
                     "--pids-limit", str(cfg.get("lab.pids_limit", 1024))]
        for cap in cfg.get("lab.extra_caps", []) or []:
            args += ["--cap-add", str(cap)]
        for dev in cfg.get("lab.devices", []) or []:
            if Path(dev).exists():
                args += ["--device", dev]
        if cfg.get("lab.systemd", True):
            args += ["--systemd", "always", self.image, "/sbin/init"]
        else:
            args += ["--init", self.image, "sleep", "infinity"]
        return args

    def ensure_running(self, progress: Progress = None) -> None:
        say = progress or (lambda m: None)
        info = self._inspect()
        if info is None:
            if not self.image_present():
                raise LabError("The laboratory image is missing. Build it from the Lab menu "
                               "or run: linux-tutor-lab build")
            say("Creating your laboratory system...")
            cp = self._podman(*self._run_args(True), timeout=180)
            if cp.returncode != 0 and re.search(r"cgroup|controller|memory|cpu", cp.stderr, re.I):
                # Some hosts do not delegate cgroup controllers to rootless users.
                self.warnings.append("Resource limits are unavailable on this host "
                                     "(cgroup delegation); the lab runs without them.")
                log.warning("retrying lab creation without resource limits: %s", cp.stderr.strip())
                self._podman("rm", "-f", self.name, timeout=60)
                cp = self._podman(*self._run_args(False), timeout=180)
            if cp.returncode != 0:
                raise LabError(f"Could not create the laboratory: {cp.stderr.strip()}")
            fresh = True
        else:
            fresh = False
            if not info.get("State", {}).get("Running"):
                say("Starting your laboratory system...")
                self._podman("start", self.name, timeout=120, check=True)
        self._wait_ready(say)
        if fresh:
            self._first_boot()

    def _wait_ready(self, say) -> None:
        if not self.config.get("lab.systemd", True):
            return
        say("Waiting for the laboratory to boot...")
        deadline = time.monotonic() + 90
        state = ""
        while time.monotonic() < deadline:
            cp = self._podman("exec", self.name, "systemctl", "is-system-running", timeout=20)
            state = cp.stdout.strip()
            if state in ("running", "degraded"):
                return
            time.sleep(0.5)
        raise LabError(f"The laboratory did not finish booting (state: {state or 'unknown'}).")

    def _first_boot(self) -> None:
        net = self.config.get("lab.network", "none") or "none"
        mode = "offline" if net == "none" else "online"
        self.exec(f"/usr/local/sbin/lab-netmode {mode} --no-update; : > /var/lib/tutor/cmdlog",
                  timeout=60)

    def reset(self, progress: Progress = None) -> None:
        say = progress or (lambda m: None)
        say("Removing the old laboratory...")
        self._podman("rm", "-f", "-t", "2", self.name, timeout=120)
        self.ensure_running(progress)
        say("The laboratory has been reset to a clean state.")

    def stop(self) -> None:
        if self._inspect():
            self._podman("stop", "-t", "3", self.name, timeout=60)

    def remove(self) -> None:
        self._podman("rm", "-f", "-t", "2", self.name, timeout=120)

    # ------------------------------------------------------------------ execution
    def exec(self, script: str, user: str = "root", timeout: float | None = None,
             stdin: str | None = None) -> ExecResult:
        args = ["exec", "-i", "-u", user]
        if user == self.student_user:
            args += ["-w", self.student_home, "-e", f"HOME={self.student_home}",
                     "-e", f"USER={user}", "-e", f"LOGNAME={user}"]
        args += [self.name, "bash", "-c", script]
        try:
            cp = self._podman(*args, timeout=timeout or self.timeout, input=stdin or "")
        except LabError:
            raise
        if cp.returncode in (125, 126, 127) and ("no such container" in cp.stderr.lower()
                                                 or "not running" in cp.stderr.lower()):
            raise LabError(cp.stderr.strip())
        return ExecResult(cp.returncode, cp.stdout, cp.stderr)

    def shell_argv(self, user: str | None = None) -> list[str]:
        user = user or self.student_user
        workdir = self.student_home if user == self.student_user else "/root"
        return [podman_path() or "podman", "exec", "-it", "-u", user, "-w", workdir,
                "-e", "TERM=xterm-256color", "-e", f"HOME={workdir}",
                "-e", f"USER={user}", "-e", f"LOGNAME={user}",
                "-e", "LANG=C.UTF-8", self.name, "bash", "-l"]


# ---------------------------------------------------------------------- image management
def build_image(config, progress: Progress = None, base_image: str | None = None,
                build_dir: Path | None = None) -> None:
    say = progress or (lambda m: None)
    exe = podman_path()
    if not exe:
        raise LabError("Podman is not installed. Install it with: sudo apt install podman")
    build_dir = build_dir or paths.lab_build_dir()
    image = f"{config.get('lab.image')}:{LAB_IMAGE_VERSION}"
    args = [exe, "build", "--pull=missing", "-t", image,
            "--build-arg", f"LAB_VERSION={LAB_IMAGE_VERSION}"]
    if base_image:
        args += ["--build-arg", f"BASE_IMAGE={base_image}"]
    args.append(str(build_dir))
    say(f"Building {image} (this needs internet access and takes several minutes)...")
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors="replace")
    assert proc.stdout
    for line in proc.stdout:
        say(line.rstrip())
    if proc.wait() != 0:
        raise LabError("Building the laboratory image failed (see the output above).")
    say("Laboratory image built successfully.")


def export_image(config, dest: Path) -> None:
    image = f"{config.get('lab.image')}:{LAB_IMAGE_VERSION}"
    cp = subprocess.run([podman_path() or "podman", "save", "--format", "oci-archive",
                         "-o", str(dest), image], capture_output=True, text=True)
    if cp.returncode != 0:
        raise LabError(cp.stderr.strip())


def import_image(config, src: Path) -> None:
    image = f"{config.get('lab.image')}:{LAB_IMAGE_VERSION}"
    cp = subprocess.run([podman_path() or "podman", "load", "-i", str(src)],
                        capture_output=True, text=True)
    if cp.returncode != 0:
        raise LabError(cp.stderr.strip())
    loaded = re.findall(r"Loaded image\(?s?\)?:\s*(\S+)", cp.stdout)
    if loaded and image not in loaded:
        subprocess.run([podman_path() or "podman", "tag", loaded[0], image], capture_output=True)
    if subprocess.run([podman_path() or "podman", "image", "exists", image]).returncode != 0:
        raise LabError(f"The archive did not contain {image}")


def list_lab_containers() -> list[dict]:
    if not podman_path():
        return []
    cp = subprocess.run([podman_path(), "ps", "-a", "--filter", "label=org.linuxtutor.managed=true",
                         "--format", "json"], capture_output=True, text=True)
    try:
        return json.loads(cp.stdout or "[]")
    except json.JSONDecodeError:
        return []
