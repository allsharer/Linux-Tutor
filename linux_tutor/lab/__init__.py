"""The isolated Linux laboratory (execution environment).

`LabBackend` is the interface the rest of the application uses.  `PodmanLab` is the
production implementation (rootless Podman).  Other technologies (e.g. a VM backend)
can be added by implementing the same interface.
"""
from __future__ import annotations

from .base import ExecResult, LabBackend, LabError, LabStatus

LAB_IMAGE_VERSION = "1"

__all__ = ["ExecResult", "LabBackend", "LabError", "LabStatus", "LAB_IMAGE_VERSION", "create_lab"]


def create_lab(config, profile_key: str, kind: str = "lesson") -> LabBackend:
    engine = config.get("lab.engine", "podman")
    if engine == "podman":
        from .podman import PodmanLab
        return PodmanLab(config, profile_key, kind)
    raise LabError(f"unsupported laboratory engine {engine!r}")
