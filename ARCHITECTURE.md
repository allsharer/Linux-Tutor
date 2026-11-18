# Architecture

## Technology choices

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3** (≥ 3.10, tested on 3.12 and 3.14) | Ubuntu ships it; excellent for orchestration, text and process handling; readable for contributors |
| GUI | **PySide6 / Qt 6 Widgets** | native desktop application, packaged in Ubuntu (`python3-pyside6.*`), mature splitters/tabs/text rendering; no web engine needed |
| Terminal emulator | **pyte** (VT100/xterm state machine, Ubuntu package) + a custom Qt widget | gives a real terminal (colours, cursor keys, alternate screen for `less`/`vim`/`top`, tab completion) without shipping a browser engine |
| Shell | **Bash** inside the laboratory | the standard Linux shell; `bash -l` via `podman exec -it` on a PTY |
| Isolation | **rootless Podman** running an Ubuntu 24.04 image with **systemd as PID 1** | no daemon, no root on the host, user namespaces; systemd makes `systemctl`, `journalctl`, timers, cron and sshd behave like a real server |
| Records | **SQLite** (Python stdlib) | single file, transactional, zero administration, survives lab resets |
| Curriculum | **YAML** files (+ Markdown in lecture text) | human-editable, diff-friendly; ready for a future curriculum editor |
| Configuration | layered **JSON** (defaults < /etc < ~/.config) | instructors can lock settings such as the pass mark |
| Packaging | **.deb** (`dpkg-deb`) + `install.sh` + offline image archive | native on Ubuntu; dependencies resolved by apt |

Alternatives considered: Electron/xterm.js (heavier, needs Node and a browser engine);
QtWebEngine + xterm.js (≈ 200 MB dependency); Docker (root daemon); LXD/VMs (much heavier
per student, slower reset; kept as a possible future backend); chroot/bubblewrap (no
systemd, weaker teaching of services and users).

## Components

```
linux_tutor/
├── app.py              entry point: logging, config, curriculum, profile chooser, main window
├── cli.py              linux-tutor-lab: build/import/export/test/reset/check/validate
├── paths.py            every filesystem location (XDG), overridable by environment
├── config.py           layered configuration with instructor locks
├── curriculum/         (2) curriculum & lesson management
│   ├── models.py         Lesson, Section, Exercise, Question, Exam, Level, Module
│   └── loader.py         YAML loading + validation (unknown check types, bad answers...)
├── lab/                (4) Linux execution environment
│   ├── base.py           LabBackend interface: status, ensure_running, exec, shell_argv, reset
│   └── podman.py         rootless Podman implementation, image build/import/export
├── terminal/           (3) terminal & shell management
│   └── pty_session.py    PTY + child process (podman exec -it ... bash -l), UI-independent
├── assessment/         (5) assessment engine
│   ├── checks.py         registry of outcome checks (@check decorator) + plugin loader
│   └── engine.py         prepare/evaluate, outcome classification, diagnostics, method notes
├── exams/              (7) examination engine
│   └── engine.py         AssessmentSession, theory grading, exam assembly, results
├── progress/           (6) student progress management
│   ├── store.py          SQLite schema, records, export/import, backup/restore
│   └── progression.py    unlock rules, dashboard overview, competency
└── ui/                 (1) user interface (PySide6)
    ├── main_window.py    layout, menus, lab lifecycle, flows between views
    ├── lecture_view.py   paged lecture with "Try it", "Explain further"
    ├── exercise_panel.py exercises with hints and feedback
    ├── practical.py      shared practical-task widget
    ├── assessment_view.py quizzes/exams and result reports
    ├── nav_panel.py      course tree with status icons
    ├── pages.py          dashboard, practice mode, exam intro, welcome
    ├── terminal_widget.py pyte-based terminal emulator
    ├── dialogs.py        profiles, settings, glossary, lab management
    ├── render.py/theme.py Markdown→HTML, call-out boxes, dark/light themes
    └── workers.py        background tasks (keeps the UI responsive)
```

Component (8), configuration and settings, is `config.py` + `paths.py`.

The UI depends on everything; nothing below `ui/` imports Qt.  `curriculum`, `lab`,
`assessment`, `exams` and `progress` are plain Python and could serve a web front end: the
PTY file descriptor in `terminal/pty_session.py` can be relayed over a WebSocket, and all
other operations are function calls.

## Key flows

**Starting the lab.** `PodmanLab.ensure_running()` creates the container on first use
(`podman run -d --systemd always --network none --memory ... --pids-limit ...`), waits for
`systemctl is-system-running` to report running/degraded, then runs a health check as
`student`.  Containers are named `linux-tutor-<lesson|practice>-<profile id>-<username>`, so
each profile has its own lesson lab and practice lab.  Containers persist between sessions
(stopped on exit) until reset.

**Terminal.** `TerminalWidget.start(lab.shell_argv())` spawns `podman exec -it -u student
... bash -l` on a new PTY.  Keystrokes go to the PTY; output is fed into a pyte screen and
painted.  Window resizes propagate (TIOCSWINSZ → SIGWINCH → podman → container PTY).

**Exercise.** *Set up task* runs the exercise's `setup` script as root in the lab and
records the current length of the command log `/var/lib/tutor/cmdlog` (written by a
`PROMPT_COMMAND` hook in the lab's bash).  *Check my work* runs every `checks` entry (state
inspection via `podman exec`), then `constraints`; on failure the `diagnostics` explain
what happened.  The command log is used only to say "you used a different method from the
lesson" - never to mark.

**Assessment.** `lesson_session()`/`exam_session()` build an `AssessmentSession`.
Practical questions are prepared and evaluated through the same engine; theory questions
are graded in `grade_theory()`.  The `SessionResult` (score, pass/retry, explanations,
revision topics) is stored in SQLite and drives the progression rules.

## Design decisions (ADR summary)

1. **Mark the state, not the keystrokes.**  Every check inspects the laboratory.  This is
   what makes alternative methods acceptable and makes "typing the right-looking command"
   worthless if it did not work.
2. **Records outside the lab.**  The database lives on the host in the user's XDG data
   directory, so a lab reset or deletion can never lose academic progress.
3. **One lab per profile, plus a separate practice lab.**  Experiments in practice mode
   cannot disturb lesson exercises; students never see each other's work.
4. **systemd inside the container.**  Required to teach services, timers, journald, cron
   and sshd realistically.  Podman's `--systemd always` supports it rootless.
5. **Offline by default.**  `--network none`; an offline apt repository inside the image
   makes the package-management lessons work without Internet access.
6. **Curriculum as data.**  Lessons, exercises, checks, hints and exams are YAML; adding a
   lesson requires no code.  New *kinds* of checks are one decorated function and can be
   shipped as plugins (`<curriculum>/plugins/*.py` or `~/.local/share/linux-tutor/plugins`).
7. **Every exercise is machine-tested.**  Each exercise carries a model solution and
   optionally alternatives and known-wrong attempts; `tests/lab_harness.py` proves them in
   a real lab (see TESTING.md).
8. **No development-only paths.**  `paths.py` is the single source of locations; the
   installed layout is `/usr/share/linux-tutor` (code, curriculum, lab build files),
   `/usr/bin` (launchers), `/etc/linux-tutor/config.json` (system configuration).

## Data locations

| Data | Location |
|---|---|
| Application code, curriculum, lab Containerfile | `/usr/share/linux-tutor/` |
| Launchers | `/usr/bin/linux-tutor`, `/usr/bin/linux-tutor-lab` |
| System/instructor configuration | `/etc/linux-tutor/config.json` |
| User configuration, window layout | `~/.config/linux-tutor/` |
| Student records (SQLite), backups, plugins | `~/.local/share/linux-tutor/` |
| Logs | `~/.local/state/linux-tutor/linux-tutor.log` |
| Laboratory image and containers | the user's rootless Podman storage (`~/.local/share/containers/`) |

## Extending

* **A lesson**: add a YAML file to `curriculum/levelN/`, list its id in `curriculum.yaml`,
  run `linux-tutor-lab validate` and `python3 -m tests.lab_harness <id>`.
* **A check type**: write `@check("name", required=(...))` in `assessment/checks.py` or a
  plugin file.
* **Another lab backend** (e.g. a VM for LVM/kernel-module labs): implement `LabBackend` and
  register it in `lab/__init__.py:create_lab`; select it with `lab.engine` in the config.
* **A web UI**: reuse every package except `ui/`.
