# CLAUDE.md - project instructions for developers and coding agents

## What this is

**Linux Tutor**: an Ubuntu desktop application that teaches Linux (Beginner →
Intermediate → Advanced) with lectures, a real Bash shell in an isolated rootless-Podman
laboratory, outcome-based marking of practical work, progressive hints, assessments,
level examinations and progress tracking.  The original requirements are in `prompt.txt`.

## Golden rules

1. **Mark outcomes, never keystrokes.**  Checks inspect lab state.  The command log
   (`/var/lib/tutor/cmdlog`) is only used to say "alternative method" or for diagnostics.
2. **Student commands never run on the host.**  Everything goes through
   `LabBackend.exec()` / `shell_argv()` (podman exec).
3. **Records live on the host** (`paths.database_file()`); labs are disposable.
4. **No hard-coded paths, users or hostnames** outside `linux_tutor/paths.py`.  The
   sandbox is a dev facility only; the deliverable is the `.deb`/release bundle.
5. **Curriculum is data** (YAML).  Every practical task needs 4 hints, a working
   `reference`/`solution`, and must pass `python3 -m tests.lab_harness <id>`.
6. **Qt only via `linux_tutor/ui/qt.py`**, fully-qualified enums (PyQt6 and PySide6 must
   both work - Ubuntu 24.04 has only PyQt6).

## Layout

| Path | Component |
|---|---|
| `linux_tutor/ui/` | (1) user interface |
| `linux_tutor/curriculum/` + `curriculum/` | (2) curriculum model/loader + content |
| `linux_tutor/terminal/` + `ui/terminal_widget.py` | (3) terminal & shell |
| `linux_tutor/lab/` + `lab/` | (4) execution environment (Podman) + image definition |
| `linux_tutor/assessment/` | (5) assessment engine |
| `linux_tutor/progress/` | (6) student progress |
| `linux_tutor/exams/` | (7) examination engine |
| `linux_tutor/config.py`, `paths.py` | (8) configuration |
| `tests/` | pytest suite, `lab_harness.py`, `acceptance.py` |
| `scripts/` | build-deb, build-release, install, uninstall, YAML lint/quote fixer, catalogue |
| `packaging/` | launchers, desktop file, icon, Debian control/maintainer scripts |

## Everyday commands

```bash
python3 -m linux_tutor                       # run from source
python3 -m linux_tutor.cli build|check|validate|test|status|reset USER|remove-all
python3 -m pytest -q                         # all tests (lab tests need the image)
python3 -m tests.lab_harness [GLOB...] [--keep]   # verify practical tasks in a real lab
QT_QPA_PLATFORM=offscreen python3 tests/acceptance.py all   # end-to-end, real lab + GUI
scripts/lint-yaml.sh; python3 scripts/fix-yaml-quotes.py curriculum/*/*.yaml
scripts/build-deb.sh; scripts/build-release.sh --with-image
```

Use `LINUX_TUTOR_USER_DATA_DIR` etc. (not `XDG_DATA_HOME`) to isolate test data - XDG
changes would also move Podman's storage.

## Pitfalls learned the hard way

* `pkill -f PATTERN` inside a lab setup script kills the setup script itself (its
  command line contains the pattern).  Use `pkill -x NAME`, copies of binaries with unique
  names, or patterns anchored at `^` that cannot match `bash -c ...`.
* Ubuntu's AppArmor profile `nc.openbsd` attaches by path even inside rootless containers
  and blocks signals to `nc`; copy the binary to a unique name for services in exercises.
* `/etc/hosts` in the lab is a bind mount: `sed -i` fails; rewrite it with `cat > /etc/hosts`.
* `ip netns exec` fails in the lab (cannot remount /sys); use `nsenter --net=/run/netns/NS`.
* Bash cannot trap signals that were ignored on entry (`nohup`); start trap-based demo
  daemons with `setsid`.
* YAML: quote plain scalars containing `: ` (e.g. `cut -d: -f1`), `?`, `[`, `#`.
* `/proc/sys` is read-only under Podman; the image's `tutor-procsys.service` remounts it
  rw (namespaced `net.*` keys only become writable).
* Lab image changes require bumping `LAB_IMAGE_VERSION`.

## Status (2026-11-18)

**Complete (v1.0.0):** all phases of the brief.

* Architecture and documentation: README, ARCHITECTURE, SECURITY, CURRICULUM, ASSESSMENT,
  DEVELOPMENT, TESTING, CHANGELOG, INSTALL, BUILD, DEPLOYMENT, UNINSTALL, DEPENDENCIES,
  BACKUP-RESTORE.
* Application, lab, terminal, assessment engine, exams, progress, config - implemented.
* Curriculum: 65 lessons, 157 exercises, 439 questions, 4 exams, 91 glossary terms - all
  practical tasks verified by the harness (242/242 in the sandbox with Podman 5.7 and on a clean Ubuntu 24.04 with Podman 4.9.3).
* Packaging: `.deb`, install/uninstall scripts, release bundle with offline image.
* Clean-system deployment verified on fresh Ubuntu 24.04.5 (LXD container).

## Outstanding / ideas

* VM-based `LabBackend` (e.g. QEMU/LXD VM) to make LVM, loop devices, kernel modules and
  GRUB fully practical; currently taught with config files and real tool output.
* Curriculum editor UI (the model and validator are ready for it).
* Optional web front end reusing the non-UI packages (relay the PTY over WebSocket).
* Instructor dashboard aggregating several students' exported progress files.
* More translations; accessibility review with a screen reader.
* Choose a licence (none chosen yet).
