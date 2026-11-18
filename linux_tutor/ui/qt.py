"""Qt binding selection.

Linux Tutor runs with either **PySide6** or **PyQt6**:

* Ubuntu 24.04 LTS packages PyQt6 (python3-pyqt6) but not PySide6;
* Ubuntu 25.04+ packages both.

PySide6 is preferred when importable; set ``LINUX_TUTOR_QT=pyqt6`` (or ``pyside6``) to force a
binding.  All UI modules import Qt names from here and use fully-qualified enums
(``Qt.Orientation.Horizontal``), which both bindings accept.
"""
from __future__ import annotations

import os

_wanted = os.environ.get("LINUX_TUTOR_QT", "").strip().lower()
API = ""

if _wanted in ("", "pyside6"):
    try:
        from PySide6.QtCore import *  # noqa: F401,F403
        from PySide6.QtGui import *  # noqa: F401,F403
        from PySide6.QtWidgets import *  # noqa: F401,F403
        from PySide6.QtCore import Signal, Slot  # noqa: F401
        API = "PySide6"
    except ImportError:
        if _wanted == "pyside6":
            raise

if not API:
    from PyQt6.QtCore import *  # noqa: F401,F403
    from PyQt6.QtGui import *  # noqa: F401,F403
    from PyQt6.QtWidgets import *  # noqa: F401,F403
    from PyQt6.QtCore import pyqtSignal as Signal, pyqtSlot as Slot  # noqa: F401
    API = "PyQt6"
