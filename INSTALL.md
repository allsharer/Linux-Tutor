# Installing Linux Tutor

Linux Tutor is a desktop application for **Ubuntu 24.04 LTS or newer** (tested on 24.04.5
and 26.04).  It needs about 1.5 GB of disk space per user for the laboratory image and
2 GB of RAM or more.

There are three ways to install it.

## 1. Automated installation (recommended)

From a release bundle `linux-tutor-<version>.tar.gz`:

```bash
tar xzf linux-tutor-1.0.0.tar.gz
cd linux-tutor-1.0.0
sha256sum -c SHA256SUMS          # optional: verify the files
./install.sh
```

Run it as **your normal user** (it calls `sudo` for the system-wide steps).  The script:

1. checks the Ubuntu version;
2. installs the `.deb` package with `apt`, which pulls in every dependency
   (Podman, PyQt6 or PySide6, pyte, PyYAML, Markdown, uidmap);
3. makes sure your account has subordinate UID/GID ranges for rootless Podman;
4. prepares **your** laboratory: imports the bundled image
   `linux-tutor-lab-image-*.tar.gz` if present (offline), otherwise builds it
   (`linux-tutor-lab build`, needs Internet access, about 5 minutes);
5. verifies everything with `linux-tutor-lab check` (it starts a test laboratory).

Options: `./install.sh --lab-image FILE` uses a specific image archive;
`./install.sh --no-lab` installs only the application.

Other users of the same computer only need to prepare their own laboratory once:

```bash
linux-tutor-lab import /path/to/linux-tutor-lab-image-1.tar.gz    # or: linux-tutor-lab build
```

(The application also offers to build it on first start.)

## 2. Installing the .deb manually

```bash
sudo apt install ./linux-tutor_1.0.0_all.deb      # note the ./ - apt resolves dependencies
linux-tutor-lab build                              # as your user, not root
linux-tutor-lab check
```

## 3. Running from source (developers)

```bash
sudo apt install podman uidmap python3-pyqt6 python3-pyte python3-yaml python3-markdown
git clone <repository> linux-tutor && cd linux-tutor
python3 -m linux_tutor.cli build      # build the laboratory image
python3 -m linux_tutor.cli check
python3 -m linux_tutor                # start the application
```

## Starting

* Applications menu → **Linux Tutor**, or
* `linux-tutor` in a terminal (`linux-tutor --profile NAME` opens a profile directly,
  `linux-tutor --check` runs the installation check).

## What gets installed where

| Path | Contents |
|---|---|
| `/usr/bin/linux-tutor`, `/usr/bin/linux-tutor-lab` | launchers |
| `/usr/share/linux-tutor/` | application code, curriculum, laboratory Containerfile |
| `/usr/share/applications/linux-tutor.desktop` | menu entry |
| `/usr/share/icons/hicolor/scalable/apps/linux-tutor.svg` | icon |
| `/etc/linux-tutor/config.json` | system/instructor configuration (kept on upgrade) |
| `~/.local/share/linux-tutor/` | **your** student records (never touched by the package) |
| `~/.config/linux-tutor/` | your settings |
| `~/.local/share/containers/` | your Podman image and laboratory containers |

## Instructor configuration

Edit `/etc/linux-tutor/config.json` (JSON).  Example - require 85 % everywhere, forbid
students from lowering it, enable the lab network:

```json
{
  "assessment": { "passing_score": 85, "exam_passing_score": 85 },
  "lab": { "network": "pasta" },
  "instructor": { "locked": ["assessment.passing_score", "assessment.exam_passing_score", "lab.network"] }
}
```

All keys and defaults are listed in `linux_tutor/config.py` (`DEFAULTS`).  Notable ones:
`lab.memory` (default `1g`), `lab.cpus` (`1.5`), `lab.pids_limit` (`1024`),
`lab.extra_caps`, `assessment.practical_weight` (`2.0`), `assessment.allow_hints_in_exams`
(`false`), `instructor.unlock_all` (open every lesson - for demonstrations).

## Troubleshooting

| Problem | Fix |
|---|---|
| `linux-tutor-lab check`: Podman does not work for this user | `grep $USER /etc/subuid /etc/subgid` must show a range; add one with `sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $USER`, then `podman system migrate` |
| "The laboratory image is missing" | `linux-tutor-lab build` (Internet) or `linux-tutor-lab import FILE` |
| Building fails to download | check Internet access/proxy; or build on another machine and copy the image archive (`linux-tutor-lab export FILE`) |
| Warning "Resource limits are unavailable" | your login session does not delegate cgroup controllers (common over plain `su`); log in graphically or via SSH. The lab still works, without limits |
| Lab will not start after an upgrade of Podman | `linux-tutor-lab remove-all`, then start Linux Tutor again (records are unaffected) |
| Terminal shows "session ended" | press Enter, or Lab → Reconnect terminal |
| Anything else | `linux-tutor --verbose`, and the log `~/.local/state/linux-tutor/linux-tutor.log` |
