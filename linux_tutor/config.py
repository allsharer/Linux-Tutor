"""Configuration and settings.

Settings are layered: built-in defaults < system file (/etc/linux-tutor/config.json,
written by an instructor or administrator) < user file (~/.config/linux-tutor/config.json).
Keys listed in ``INSTRUCTOR_LOCKED`` can be locked by the system file so that
students cannot lower the passing score, for example.
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "assessment": {
        "passing_score": 80,          # percent, lesson assessments
        "exam_passing_score": 80,     # percent, level and final examinations
        "practical_weight": 2.0,      # practical questions count double by default
        "allow_hints_in_exams": False,
    },
    "lab": {
        "engine": "podman",
        "image": "localhost/linux-tutor-lab",
        "network": "none",            # "none" (default) or "slirp" / "pasta" for internet access
        "memory": "1g",
        "cpus": "1.5",
        "pids_limit": 1024,
        "systemd": True,
        "extra_caps": ["NET_ADMIN", "NET_RAW", "SYS_ADMIN", "AUDIT_WRITE"],
        "devices": ["/dev/fuse"],
        "command_timeout": 60,
    },
    "ui": {
        "theme": "dark",              # "dark" | "light"
        "font_size": 11,
        "terminal_font_size": 11,
        "terminal_font": "Monospace",
        "show_welcome": True,
    },
    "instructor": {
        "locked": [],                 # dotted keys the user file may not override
        "unlock_all": False,          # testing/instructor mode: ignore progression locks
    },
}


def _deep_merge(base: dict, override: dict, locked: set[str], prefix: str = "") -> dict:
    for key, value in override.items():
        dotted = f"{prefix}{key}"
        if dotted in locked:
            log.info("setting %s is locked by the instructor configuration", dotted)
            continue
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value, locked, dotted + ".")
        else:
            base[key] = value
    return base


def _read_json(path: Path) -> dict:
    try:
        with path.open() as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("ignoring unreadable configuration %s: %s", path, exc)
        return {}


class Config:
    def __init__(self, user_file: Path | None = None, system_file: Path | None = None):
        self.user_file = user_file or paths.config_dir() / "config.json"
        self.system_file = system_file or paths.system_config_file()
        self.reload()

    def reload(self) -> None:
        self._system = _read_json(self.system_file)
        self._user = _read_json(self.user_file)
        merged = copy.deepcopy(DEFAULTS)
        _deep_merge(merged, self._system, set())
        self.locked = set(merged.get("instructor", {}).get("locked", []))
        _deep_merge(merged, self._user, self.locked)
        self.data = merged

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        if dotted in self.locked:
            raise PermissionError(f"{dotted} is locked by the instructor configuration")
        node = self._user
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self.save()
        self.reload()

    def save(self) -> None:
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.user_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._user, indent=2, sort_keys=True))
        tmp.replace(self.user_file)
