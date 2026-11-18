"""Filesystem locations, following the XDG base-directory specification.

Nothing in the application may hard-code an absolute path outside this module.
Every location can be overridden with an environment variable, which the test
suite and the development launcher use to keep data out of the real profile.

    Application data (read-only)   LINUX_TUTOR_DATA_DIR    curriculum/, lab/
    System configuration           /etc/linux-tutor/config.json
    User configuration             $XDG_CONFIG_HOME/linux-tutor/config.json
    Student records                $XDG_DATA_HOME/linux-tutor/  (tutor.db, backups/)
    Regenerable cache              $XDG_CACHE_HOME/linux-tutor/
    Logs                           $XDG_STATE_HOME/linux-tutor/linux-tutor.log
"""
from __future__ import annotations

import os
from pathlib import Path

from . import APP_ID

_PACKAGE_DIR = Path(__file__).resolve().parent


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / default


def data_dir() -> Path:
    """Directory holding the read-only application data (curriculum, lab build files).

    Search order: $LINUX_TUTOR_DATA_DIR, the source tree (development checkout),
    then the installed locations under /usr/share and /usr/local/share.
    """
    env = os.environ.get("LINUX_TUTOR_DATA_DIR")
    candidates = [Path(env)] if env else []
    candidates += [
        _PACKAGE_DIR.parent,                         # source checkout / /opt/linux-tutor
        Path("/usr/share") / APP_ID,
        Path("/usr/local/share") / APP_ID,
    ]
    for c in candidates:
        if (c / "curriculum" / "curriculum.yaml").is_file():
            return c
    raise FileNotFoundError(
        "Linux Tutor curriculum not found. Set LINUX_TUTOR_DATA_DIR or reinstall the application."
    )


def curriculum_dir() -> Path:
    env = os.environ.get("LINUX_TUTOR_CURRICULUM_DIR")
    return Path(env) if env else data_dir() / "curriculum"


def lab_build_dir() -> Path:
    return data_dir() / "lab"


def system_config_file() -> Path:
    return Path(os.environ.get("LINUX_TUTOR_SYSTEM_CONFIG", f"/etc/{APP_ID}/config.json"))


def _override(var: str) -> Path | None:
    v = os.environ.get(var)
    return Path(v) if v else None


# LINUX_TUTOR_*_DIR variables relocate only Linux Tutor's own files (used by the test
# suite).  Changing XDG_DATA_HOME instead would also move Podman's image storage.
def config_dir() -> Path:
    return _override("LINUX_TUTOR_CONFIG_DIR") or _xdg("XDG_CONFIG_HOME", ".config") / APP_ID


def user_data_dir() -> Path:
    return _override("LINUX_TUTOR_USER_DATA_DIR") or _xdg("XDG_DATA_HOME", ".local/share") / APP_ID


def cache_dir() -> Path:
    return _override("LINUX_TUTOR_CACHE_DIR") or _xdg("XDG_CACHE_HOME", ".cache") / APP_ID


def state_dir() -> Path:
    return _override("LINUX_TUTOR_STATE_DIR") or _xdg("XDG_STATE_HOME", ".local/state") / APP_ID


def database_file() -> Path:
    return user_data_dir() / "tutor.db"


def backup_dir() -> Path:
    return user_data_dir() / "backups"


def log_file() -> Path:
    return state_dir() / "linux-tutor.log"


def ensure_user_dirs() -> None:
    for d in (config_dir(), user_data_dir(), backup_dir(), cache_dir(), state_dir()):
        d.mkdir(parents=True, exist_ok=True)
        try:
            d.chmod(0o700)
        except OSError:
            pass
