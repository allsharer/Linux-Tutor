# Linux Tutor

**An interactive, hands-on Linux learning and assessment environment** - a modern take on
the classic DOS Tutor programs of the 1980s and 1990s.

Linux Tutor combines three things in one desktop application for Ubuntu:

* **a personal instructor** - 65 structured lessons in three levels (Beginner, Intermediate,
  Advanced), presented one manageable page at a time, with examples you can send straight
  to the terminal, "explain further" pages and a glossary;
* **a real Linux laboratory** - a genuine Bash shell in an isolated, disposable Ubuntu
  system (rootless Podman container with systemd) where students can do *anything*,
  including administrative work with `sudo`, without any risk to the host computer;
* **an intelligent examiner** - practical exercises are marked on the **resulting system
  state**, not on the commands typed, so every valid method is accepted; mistakes get
  specific, educational explanations; hints come in four progressive stages; every lesson
  ends with an assessment and every level with an examination.

```
 +-----------------+--------------------------------------+-----------------+
 |  Course         |  Lecture / assessment / dashboard    |  Exercises,     |
 |  navigation     |                                      |  hints and      |
 |  (levels,       +--------------------------------------+  feedback       |
 |  lessons,       |  Terminal: real Bash in the isolated |                 |
 |  exams)         |  laboratory (tabs)                   |                 |
 +-----------------+--------------------------------------+-----------------+
```

## Features

* Three levels, 65 lessons, 157 practical exercises, 439 assessment questions,
  4 examinations (one per level plus a final examination), 91-term glossary
* Outcome-based assessment: files, contents, permissions, ownership, ACLs, capabilities,
  users and groups, processes, services, ports, packages, crontabs, mounts, firewall
  rules, journal entries, script behaviour and exit codes - and **safety constraints**
  that detect unwanted side effects
* Feedback that distinguishes *correct*, *correct by an alternative method*, *correct with
  side effects*, *partially complete*, *incorrect* and *cannot be verified*
* Progressive hints (concept → Linux feature → example → full explanation), recorded but
  never penalised in exercises
* Competency-based progression: a lesson unlocks only when the previous lesson's
  assessment is passed (default 80 %, instructor-configurable); levels unlock by examination
* Ungraded **Practice mode** with its own separate laboratory - break things on purpose
* Student profiles, progress dashboard, export (JSON), HTML progress report, backup/restore
* Laboratory reset in seconds without touching academic records
* Dark and light themes, adjustable font sizes, resizable panels, multiple terminal tabs
* Curriculum in YAML files - add lessons without touching the application

**Source and releases:** <https://github.com/allsharer/Linux-Tutor> - download the latest
bundle from [Releases](https://github.com/allsharer/Linux-Tutor/releases).

## Quick start

On Ubuntu 24.04 or newer, from a release bundle:

```bash
tar xzf linux-tutor-1.0.0.tar.gz && cd linux-tutor-1.0.0
./install.sh                      # installs the .deb + dependencies, prepares YOUR lab
linux-tutor                       # or start "Linux Tutor" from the applications menu
```

From a source checkout (developers):

```bash
sudo apt install podman uidmap python3-pyside6.qtwidgets python3-pyte python3-yaml python3-markdown
python3 -m linux_tutor.cli build  # build the laboratory image (once per user)
python3 -m linux_tutor            # run the application
```

See **INSTALL.md** for details, **DEPLOYMENT.md** for moving from a development machine to
a production Ubuntu system, and **UNINSTALL.md** for removal.

## Using Linux Tutor

1. Create a profile (several students can share one computer).
2. Pick a lesson in the left panel.  Read it page by page; press **Try it** next to an
   example to type it into the terminal.
3. Do the exercises on the right: **Set up task** → work in the terminal → **Check my work**.
4. Press **Start assessment** on the last page.  Pass it to unlock the next lesson.
5. After all lessons of a level, take the level examination.

| Shortcut | Action |
|---|---|
| Ctrl+Shift+C / Ctrl+Shift+V | copy / paste in the terminal |
| Shift+PgUp / Shift+PgDn | scroll the terminal history |
| Ctrl+Shift+T | new terminal tab |
| Alt+Left / Alt+Right | previous / next lecture page |
| Ctrl+D | progress dashboard |
| Ctrl+P | practice mode |
| F1 | glossary |
| F9 / F10 / F11 | toggle navigation / exercises / terminal |
| Ctrl+= / Ctrl+- | larger / smaller text |

Inside the laboratory you are user `student`; the sudo password is `student`.

## Documentation

| Document | Contents |
|---|---|
| [INSTALL.md](INSTALL.md) | production installation |
| [BUILD.md](BUILD.md) | building the package, image and release bundle |
| [DEPLOYMENT.md](DEPLOYMENT.md) | sandbox-to-production procedure |
| [UNINSTALL.md](UNINSTALL.md) | removal |
| [DEPENDENCIES.md](DEPENDENCIES.md) | runtime and build dependencies |
| [BACKUP-RESTORE.md](BACKUP-RESTORE.md) | student data backup and restore |
| [ARCHITECTURE.md](ARCHITECTURE.md) | components and design decisions |
| [SECURITY.md](SECURITY.md) | isolation model and its limits |
| [CURRICULUM.md](CURRICULUM.md) | curriculum structure and lesson format |
| [ASSESSMENT.md](ASSESSMENT.md) | how marking works |
| [DEVELOPMENT.md](DEVELOPMENT.md) | contributing, adding lessons and checks |
| [TESTING.md](TESTING.md) | test procedures and results |
| [CHANGELOG.md](CHANGELOG.md) | changes |
| [CLAUDE.md](CLAUDE.md) | project instructions, decisions and status for developers/agents |

## Licence

No licence has been chosen yet; all rights reserved by the project owner until one is added.
