import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Keep every test away from the real user's profile and configuration."""
    monkeypatch.setenv("LINUX_TUTOR_USER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LINUX_TUTOR_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LINUX_TUTOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LINUX_TUTOR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LINUX_TUTOR_SYSTEM_CONFIG", str(tmp_path / "etc-config.json"))
    monkeypatch.setenv("LINUX_TUTOR_DATA_DIR", str(ROOT))
    yield


def _lab_available() -> bool:
    if os.environ.get("LINUX_TUTOR_SKIP_LAB"):
        return False
    if not shutil.which("podman"):
        return False
    from linux_tutor.config import Config
    from linux_tutor.lab import LAB_IMAGE_VERSION
    image = f"{Config().get('lab.image')}:{LAB_IMAGE_VERSION}"
    return subprocess.run(["podman", "image", "exists", image]).returncode == 0


LAB_AVAILABLE = None


def lab_available():
    global LAB_AVAILABLE
    if LAB_AVAILABLE is None:
        LAB_AVAILABLE = _lab_available()
    return LAB_AVAILABLE


requires_lab = pytest.mark.skipif("not __import__('tests.conftest', fromlist=['x']).lab_available()",
                                  reason="Podman laboratory image not available")


@pytest.fixture(scope="session")
def lab():
    if not lab_available():
        pytest.skip("Podman laboratory image not available")
    from linux_tutor.config import Config
    from linux_tutor.lab.podman import PodmanLab
    lab = PodmanLab(Config(), "pytest", "test")
    lab.reset()
    lab.exec("echo 'student ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/zz-test && chmod 440 /etc/sudoers.d/zz-test")
    yield lab
    lab.remove()
