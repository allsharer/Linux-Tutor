# Testing

## Test suites

| Suite | Command | Needs | What it proves |
|---|---|---|---|
| Unit / core | `python3 -m pytest tests/test_core.py` | - | configuration and instructor locks, path relocation, curriculum completeness and validator, theory grading, practical weighting, store (profiles, records, export/import, backup/restore), progression (locks, unlocks, exams, instructor mode), engine outcome classes, alternative-method recognition, unverifiable handling, diagnostics, check-registry extensibility |
| GUI | `python3 -m pytest tests/test_gui.py` (offscreen) | Qt binding | lecture navigation and resume, locked lessons, assessment → record → unlock, dashboard, themes, glossary, terminal rendering, **terminal key mapping** (Ctrl+C, arrows, Tab, Alt, Ctrl+arrows); run with `LINUX_TUTOR_QT=pyqt6` and `=pyside6` |
| Lab integration | `python3 -m pytest tests/test_lab.py` | Podman + image | isolation (loopback only, no Internet/DNS, host home invisible, host-wide sysctl/clock/mounts denied, pids limit); **the same outcome via different commands receives the same mark** (the brief's `mkdir ~/projects` example and chmod octal vs symbolic); wrong location explained; partial and side-effect outcomes; a command that only *looks* right is not rewarded; a sample of curriculum tasks |
| Full curriculum | `python3 -m tests.lab_harness` (or `LINUX_TUTOR_FULL_LAB_TESTS=1 pytest tests/test_lab.py`) | Podman + image | **every** practical task: no-work → not passed; model solution → passed; every alternative method → passed; every wrong attempt → expected outcome and feedback |
| Acceptance (end-to-end) | `QT_QPA_PLATFORM=offscreen python3 tests/acceptance.py all` | full installation | a student session through the real GUI: profile, lesson, terminal typing in the real lab, exercises (right and wrong answers, hints), assessment, unlock; restart persistence; lab reset keeps records; locked lessons; practice mode with a separate lab |
| Package | `scripts/build-deb.sh --test` | dpkg-dev | package builds, metadata, byte-compilation |

`tests/conftest.py` isolates every test from the real profile (relocated data, config,
state and system-config paths).

## Results - 2026-11-18

### Development sandbox (Ubuntu 26.04, Python 3.14, Podman 5.7.0)

| Suite | Result |
|---|---|
| pytest (core + GUI + lab), PySide6 | **40 passed**, 1 skipped (the opt-in full run, covered by the harness row) |
| pytest core + GUI, PyQt6 | **25 passed** |
| Curriculum harness, all lessons and exams, fresh lab, final image | **242 / 242 practical tasks verified** in 24 min (157 exercises, 65 assessment tasks, 20 exam tasks) |
| Curriculum validator | 65 lessons, 157 exercises, 439 questions, 4 exams, 91 glossary terms, **0 warnings** |
| Acceptance, PySide6 | **29 / 29** |
| Acceptance, PyQt6 | **29 / 29** |

### Clean production-like system (fresh Ubuntu 24.04.5 LTS, Python 3.12.3, Podman 4.9.3, PyQt6 6.6.1)

Fresh LXD system container (`ubuntu:24.04`, nesting enabled), nothing pre-installed.  Only
the release bundle `linux-tutor-1.0.0.tar.gz` was copied in.

| Step | Result |
|---|---|
| `sha256sum -c SHA256SUMS` | all OK |
| `./install.sh` (apt resolved PyQt6, Podman, pyte...; offline image import) | **success** |
| `linux-tutor-lab check` | **Installation OK** (systemd in the lab: running) |
| launchers, desktop entry, icon installed | present |
| Acceptance test against `/usr/share/linux-tutor` | **29 / 29** |
| Curriculum harness on the installed curriculum (image built on the target) | **242 / 242** in 19 min |
| Acceptance test after upgrade + on-target image build | **29 / 29** |
| Uninstall (`./uninstall.sh`): package and launchers removed, `~/.local/share/linux-tutor` kept; reinstall; profile and passed lesson still present (acceptance phase 2) | **passed** |
| Upgrade install of the final bundle with the image archive withheld: `install.sh` built the lab image on the target from the packaged Containerfile (2 min 27 s), `check` OK, existing profile preserved | **passed** |

## Defects found by testing and fixed

| Defect | Found by | Fix |
|---|---|---|
| Setup scripts using `pkill -f NAME` killed themselves | harness | `pkill -x`, unique binary copies, anchored patterns; checks exclude their own shell |
| `process_absent` always failed (matched its own check shell) | harness | exclude `$$` |
| `/etc/hosts` cannot be edited with `sed -i` in Podman (bind mount) | harness | rewrite in place |
| `ip netns exec` unusable in rootless lab | manual test | lessons use `nsenter --net=` |
| `/proc/sys` read-only → sysctl lessons impossible | manual test | `tutor-procsys.service` remount (namespaced keys only) |
| AppArmor `nc.openbsd` profile made `nc` unkillable in the lab | harness | services use a renamed copy |
| Trap of SIGHUP ignored when the demo daemon started with nohup | harness | start with `setsid` |
| Several exercises accepted fewer valid variants than intended (rwX ACLs, sfdisk alignment) | harness alternatives | checks loosened to the real requirement |
| A broken symlink in an exam's setup | harness | fixed path |
| **PySide6 not packaged on Ubuntu 24.04** | clean-system test | Qt binding layer, PyQt6 support, `.deb` depends on `python3-pyqt6 \| python3-pyside6.qtwidgets` |
| Nested same-quote f-string (Python ≥ 3.12 only) | portability scan | rewritten |
| Window close raced with terminal auto-reconnect | acceptance | `_closing` guard, tolerant worker signals, health-check retry |
| Theme switch left old colours in exercise feedback | screenshot review | re-render on restyle |
| Containerfile `... && mandb -q \|\| true` could mask a failed `apt-get install` | review | optional commands grouped `{ cmd \|\| true; }` |

## Manual / usability checks

Screenshots of the main window (dark and light themes, lecture, terminal with colours,
exercise feedback, assessment, dashboard) were reviewed under both Qt bindings.  The
layout follows the brief: navigation left, lecture top, terminal bottom, exercises right;
all panels resizable and toggleable (F9/F10/F11); font size adjustable (Ctrl+= / Ctrl+-).

Not automated: screen-reader accessibility, very small screens (< 1280×800), HiDPI
scaling on a physical display.
