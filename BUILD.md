# Building Linux Tutor

All builds run as a normal user on Ubuntu (24.04 or newer).  Nothing in the build depends
on paths of the development machine.

## Prerequisites

```bash
sudo apt install dpkg-dev rsync python3 podman uidmap \
                 python3-pyqt6 python3-pyte python3-yaml python3-markdown python3-pytest
```

## 1. Check the source

```bash
python3 -m linux_tutor.cli validate          # curriculum: 0 warnings expected
scripts/lint-yaml.sh                         # YAML syntax only (fast)
python3 -m pytest -q                         # unit, GUI and lab integration tests
```

## 2. The Debian package

```bash
scripts/build-deb.sh            # -> dist/linux-tutor_<version>_all.deb
scripts/build-deb.sh --test     # also prints the package info and runs the non-lab tests
```

The package is architecture-independent (`all`).  Version comes from
`linux_tutor/__init__.py` (`__version__`).  The script stages the files under
`build/deb/`, writes `DEBIAN/control` (from `packaging/debian/control.in`), `md5sums`,
`conffiles`, maintainer scripts, and calls `dpkg-deb --root-owner-group`.

## 3. The laboratory image

The image is defined by `lab/Containerfile` and the files in `lab/files/`.

```bash
python3 -m linux_tutor.cli build               # = linux-tutor-lab build
python3 -m linux_tutor.cli test                # start a throw-away lab and health-check it
python3 -m linux_tutor.cli export lab.tar      # archive for offline installs
```

Image tag: `localhost/linux-tutor-lab:<LAB_IMAGE_VERSION>` (see
`linux_tutor/lab/__init__.py`).  **Bump `LAB_IMAGE_VERSION` whenever the Containerfile
or lab files change**; existing labs then report that they were created from an older
image and students are offered a reset.

The base image defaults to `docker.io/library/ubuntu:24.04`; override with
`linux-tutor-lab build --base IMAGE` (e.g. a local mirror).

## 4. The release bundle

```bash
scripts/build-release.sh                 # .deb + install/uninstall scripts + docs
scripts/build-release.sh --with-image    # ... plus the exported laboratory image (offline installs)
```

Output: `dist/linux-tutor-<version>/` and `dist/linux-tutor-<version>.tar.gz`, with a
`SHA256SUMS` file.  The exported image is cached as `dist/linux-tutor-lab-image-*.tar.gz`
and re-exported only when the image changes.

## 5. Verify the bundle on a clean machine

See DEPLOYMENT.md and TESTING.md: install the bundle on a fresh Ubuntu system (VM or LXD
container) and run `tests/acceptance.py` against the installed application.

## Other formats

* **AppImage / Flatpak** were considered.  Both are poor fits because the application
  must drive the *host's* rootless Podman (a sandboxed Flatpak cannot without
  `flatpak-spawn --host` and broad permissions), and Ubuntu already packages every
  dependency.  The `.deb` plus `install.sh` is the supported route; the source tree also
  runs directly with `python3 -m linux_tutor`.
