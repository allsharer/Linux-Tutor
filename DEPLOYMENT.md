# Deployment: from the development sandbox to a production Ubuntu system

The development sandbox is a build-and-test facility only.  Nothing installed on a
production machine refers to the sandbox: no sandbox paths, users, hostnames, container
volumes, registries or network services.

## What to transfer

Only the release bundle produced in the sandbox:

```
dist/linux-tutor-1.0.0.tar.gz
    linux-tutor-1.0.0/
        linux-tutor_1.0.0_all.deb              the application
        linux-tutor-lab-image-1.tar.gz         the laboratory image (optional - can be built on the target)
        install.sh  uninstall.sh               installation / removal
        SHA256SUMS                              checksums
        README.md INSTALL.md UNINSTALL.md ...   documentation
```

Nothing else is needed - in particular **not** the sandbox's Podman storage, containers,
`~/.local/share/linux-tutor` or source checkout.

## Procedure

**In the sandbox**

```bash
python3 -m pytest -q                       # all tests pass
python3 -m tests.lab_harness               # every practical task verified in a real lab
scripts/build-release.sh --with-image      # builds .deb, exports image, writes checksums
```

**Transfer** `dist/linux-tutor-1.0.0.tar.gz` to the target (USB stick, `scp`, a file share).

**On the production Ubuntu machine** (as the user who will study):

```bash
tar xzf linux-tutor-1.0.0.tar.gz && cd linux-tutor-1.0.0
sha256sum -c SHA256SUMS
./install.sh
linux-tutor
```

If the image archive is left out, `install.sh` builds the image on the target instead
(requires Internet access to `docker.io` and `archive.ubuntu.com`).

**Verify** (the same checks the acceptance test automates):

1. `linux-tutor-lab check` reports "Installation OK";
2. start Linux Tutor, create a profile;
3. open lesson 1.01, run `whoami` in the terminal, solve an exercise;
4. pass the lesson 1.01 assessment - lesson 1.02 unlocks;
5. close and restart - progress is still there;
6. Lab → Reset lesson laboratory - progress is still there, the lab is clean;
7. optionally `./uninstall.sh` and `./install.sh` again - progress is still there.

## Upgrading

Install the newer bundle with `./install.sh` (or `sudo apt install ./linux-tutor_X_all.deb`).
Student records in `~/.local/share/linux-tutor` and `/etc/linux-tutor/config.json` are kept.
If the new release has a new laboratory image version, each user imports or builds it once
(`install.sh` does this for the installing user); existing labs are offered a reset.

## Multiple users / classrooms

* Install the package once (system-wide).
* Each student should have **their own Linux account**; each runs
  `linux-tutor-lab import /shared/linux-tutor-lab-image-1.tar.gz` once (or `build`).
* Instructor settings go to `/etc/linux-tutor/config.json` (see INSTALL.md).

## Verified

This procedure was carried out from the sandbox to a **fresh Ubuntu 24.04.5 LTS system**
(LXD system container, Podman 4.9.3, Python 3.12, PyQt6 6.6) - see TESTING.md for the
recorded results.
