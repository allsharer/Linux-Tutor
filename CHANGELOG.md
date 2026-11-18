# Changelog

All notable changes to Linux Tutor.  Versions follow semantic versioning.

## [1.0.0] - 2026-11-18

First complete release.

### Application
- PySide6/PyQt6 desktop application: course navigation, paged lecture screen with
  "Try it" examples, "Explain further" and glossary; real terminal (pyte-based emulator
  on a PTY) with colours, alternate screen, scrollback, copy/paste and tabs; exercise
  panel with progressive hints; assessment and examination screens with detailed results;
  progress dashboard; practice mode; profile management; dark and light themes; adjustable
  fonts; resizable, remembered layout.
- Works with either Qt binding (`linux_tutor/ui/qt.py`): PyQt6 (Ubuntu 24.04) or PySide6.
- Student profiles, progress, attempts, hints, exam results in SQLite; JSON export/import,
  HTML report, database backup and restore.
- Layered JSON configuration with instructor-lockable settings (pass marks, lab network,
  resources); default pass mark 80 %.

### Laboratory
- Rootless Podman lab image (Ubuntu 24.04, systemd as PID 1, offline apt repository,
  fuse2fs, nftables, sshd, cron, journald); per-profile lesson lab and separate practice
  lab; network disabled by default; memory/CPU/pids limits; reset without touching
  records; build/import/export/check via `linux-tutor-lab`.

### Assessment
- Outcome-based engine with 40+ check types, safety constraints, diagnostics, outcome
  classes (correct, alternative method, side effects, partial, incorrect, unverifiable),
  check plugins.
- Theory question types: multiple choice, multiple answer, true/false, short answer
  (strings/regex), output interpretation, troubleshooting; weighted practical tasks.

### Curriculum
- 65 lessons (Beginner 20, Intermediate 23, Advanced 22), 157 exercises, 439 assessment
  questions, 3 level examinations and a final examination, 91 glossary terms.

### Packaging and tests
- `.deb` package, `install.sh`/`uninstall.sh`, release bundle with optional offline lab
  image; desktop entry and icon.
- Unit, GUI (offscreen, both Qt bindings), lab-integration and end-to-end acceptance
  tests; `tests/lab_harness.py` verifies every practical task (solution, alternatives,
  wrong attempts, no-work) in a real lab.
- Verified clean installation on Ubuntu 24.04.5 LTS (fresh system, offline image import).
