"""`linux-tutor-lab` - command-line management of the laboratory and installation.

    linux-tutor-lab status                 show engine, image and lab containers
    linux-tutor-lab build [--base IMAGE]   build the laboratory image (needs internet)
    linux-tutor-lab import FILE            load an image archive (offline install)
    linux-tutor-lab export FILE            save the image to an archive
    linux-tutor-lab test                   start a throw-away lab and run the health check
    linux-tutor-lab reset USERNAME [--practice]   reset a student's lab (records are kept)
    linux-tutor-lab remove-all             delete every Linux Tutor lab container
    linux-tutor-lab check                  verify the whole installation
    linux-tutor-lab validate [DIR]         validate a curriculum directory
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import APP_NAME, __version__, paths
from .config import Config
from .lab import LAB_IMAGE_VERSION, LabError


def _ok(msg):
    print(f"  [ OK ] {msg}")


def _bad(msg):
    print(f"  [FAIL] {msg}")


def _warn(msg):
    print(f"  [WARN] {msg}")


def check_installation(run_lab: bool = True) -> int:
    """Verify everything the application needs.  Returns a process exit status."""
    failures = 0
    print(f"{APP_NAME} {__version__} - installation check")
    print(f"  Python {sys.version.split()[0]}")
    try:
        from .ui import qt
        _ok(f"Qt bindings: {qt.API}")
    except ImportError:
        _bad("No Qt bindings - install with: sudo apt install python3-pyqt6  (or python3-pyside6.qtwidgets)")
        failures += 1
    for mod, pkg in (("pyte", "python3-pyte"), ("yaml", "python3-yaml"), ("markdown", "python3-markdown")):
        try:
            __import__(mod)
            _ok(f"Python module {mod}")
        except ImportError:
            _bad(f"Python module {mod} missing - install with: sudo apt install {pkg}")
            failures += 1
    try:
        from .curriculum.loader import load_curriculum
        cur = load_curriculum(paths.curriculum_dir())
        n_ex = sum(len(l.exercises) for l in cur.lessons.values())
        _ok(f"Curriculum at {paths.curriculum_dir()}: {len(cur.lessons)} lessons, {n_ex} exercises, "
            f"{len(cur.exams)} examinations")
        if cur.warnings:
            _warn(f"{len(cur.warnings)} curriculum warning(s); run 'linux-tutor-lab validate' for details")
    except Exception as exc:
        _bad(f"Curriculum: {exc}")
        failures += 1
    try:
        from .progress.store import ProgressStore
        paths.ensure_user_dirs()
        s = ProgressStore(paths.database_file())
        _ok(f"Student database {paths.database_file()} ({len(s.profiles())} profile(s))")
        s.close()
    except Exception as exc:
        _bad(f"Student database: {exc}")
        failures += 1

    exe = shutil.which("podman")
    if not exe:
        _bad("Podman is not installed: sudo apt install podman")
        return failures + 1
    cp = subprocess.run([exe, "info", "--format", "{{.Host.Security.Rootless}} {{.Host.CgroupsVersion}}"],
                        capture_output=True, text=True)
    if cp.returncode != 0:
        _bad(f"Podman does not work for this user: {cp.stderr.strip()[:300]}")
        return failures + 1
    rootless, cgroups = (cp.stdout.split() + ["?", "?"])[:2]
    if rootless == "true":
        _ok(f"Podman runs rootless (cgroups {cgroups})")
    else:
        _warn("Podman is NOT running rootless - Linux Tutor should be run as a normal user, not root")
    config = Config()
    image = f"{config.get('lab.image')}:{LAB_IMAGE_VERSION}"
    if subprocess.run([exe, "image", "exists", image]).returncode == 0:
        _ok(f"Laboratory image {image}")
    else:
        _bad(f"Laboratory image {image} is not installed - run: linux-tutor-lab build "
             "(or linux-tutor-lab import <archive>)")
        return failures + 1
    if run_lab:
        failures += _test_lab(config)
    print("Installation OK." if not failures else f"{failures} problem(s) found.")
    return 1 if failures else 0


def _test_lab(config) -> int:
    from .lab.podman import PodmanLab
    lab = PodmanLab(config, "selftest", "check")
    try:
        lab.ensure_running()
        problems = lab.health_check()
        r = lab.exec("systemctl is-system-running; ip -o link | wc -l; sudo -n true 2>&1 | head -1",
                     user="root")
        for p in problems:
            _bad(p)
        if not problems:
            _ok("Laboratory starts, the student account works, the filesystem is writable")
            state = r.stdout.split()[0] if r.stdout.split() else "?"
            (_ok if state in ("running", "degraded") else _warn)(f"systemd inside the laboratory: {state}")
        return len(problems)
    except LabError as exc:
        _bad(f"Laboratory could not start: {exc}")
        return 1
    finally:
        lab.remove()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="linux-tutor-lab", description="Manage the Linux Tutor laboratory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    b = sub.add_parser("build")
    b.add_argument("--base", help="base image (default: docker.io/library/ubuntu:24.04)")
    b.add_argument("--dir", type=Path, help="directory containing the Containerfile")
    i = sub.add_parser("import")
    i.add_argument("file", type=Path)
    e = sub.add_parser("export")
    e.add_argument("file", type=Path)
    sub.add_parser("test")
    r = sub.add_parser("reset")
    r.add_argument("username")
    r.add_argument("--practice", action="store_true")
    sub.add_parser("remove-all")
    sub.add_parser("check")
    v = sub.add_parser("validate")
    v.add_argument("dir", nargs="?", type=Path)
    args = ap.parse_args(argv)
    config = Config()

    from .lab import podman as pm
    try:
        if args.cmd == "status":
            image = f"{config.get('lab.image')}:{LAB_IMAGE_VERSION}"
            print(f"Podman: {pm.podman_path() or 'NOT INSTALLED'}")
            lab = pm.PodmanLab(config, "status")
            print(f"Image {image}: {'present' if lab.image_present() else 'missing'}")
            print("Laboratory containers:")
            for c in pm.list_lab_containers():
                print(f"  {c.get('Names', ['?'])[0]:45} {c.get('State', '?')}")
            return 0
        if args.cmd == "build":
            pm.build_image(config, progress=print, base_image=args.base, build_dir=args.dir)
            return 0
        if args.cmd == "import":
            pm.import_image(config, args.file)
            print("Image imported.")
            return 0
        if args.cmd == "export":
            pm.export_image(config, args.file)
            print(f"Image exported to {args.file}")
            return 0
        if args.cmd == "test":
            return _test_lab(config)
        if args.cmd == "reset":
            from .progress.store import ProgressStore
            store = ProgressStore(paths.database_file())
            p = next((p for p in store.profiles() if p.username == args.username), None)
            if not p:
                print(f"No profile {args.username!r}", file=sys.stderr)
                return 1
            lab = pm.PodmanLab(config, f"{p.id}-{p.username}", "practice" if args.practice else "lesson")
            lab.reset(print)
            lab.stop()
            return 0
        if args.cmd == "remove-all":
            for c in pm.list_lab_containers():
                name = c.get("Names", ["?"])[0]
                subprocess.run([pm.podman_path(), "rm", "-f", name], capture_output=True)
                print(f"removed {name}")
            return 0
        if args.cmd == "check":
            return check_installation()
        if args.cmd == "validate":
            from .curriculum.loader import load_curriculum
            cur = load_curriculum(args.dir or paths.curriculum_dir())
            for w in cur.warnings:
                print("WARNING:", w)
            n_ex = sum(len(l.exercises) for l in cur.lessons.values())
            n_q = sum(len(l.quiz.questions) for l in cur.lessons.values())
            print(f"{len(cur.lessons)} lessons, {n_ex} exercises, {n_q} assessment questions, "
                  f"{len(cur.exams)} exams, {len(cur.glossary)} glossary terms; {len(cur.warnings)} warnings")
            return 1 if cur.warnings else 0
    except LabError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
