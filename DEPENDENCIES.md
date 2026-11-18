# Dependencies

All runtime dependencies are standard Ubuntu packages; no pip packages, no network
services, no external registries at run time.

## Runtime (installed automatically by the .deb)

| Package | Version tested | Purpose |
|---|---|---|
| `python3` | 3.12 (24.04), 3.14 (26.04) | application language (≥ 3.10) |
| `python3-pyqt6` **or** `python3-pyside6.qtwidgets` | PyQt6 6.6.1 / 6.10.2, PySide6 6.10.2 | graphical interface (24.04 only packages PyQt6) |
| `python3-pyte` | 0.8.0 | terminal emulation |
| `python3-yaml` | 6.0 | curriculum files |
| `python3-markdown` | 3.5 | lecture text rendering |
| `podman` | 4.9.3 (24.04), 5.7.0 (26.04) | rootless containers for the laboratory |
| `uidmap` | | `newuidmap`/`newgidmap` for rootless user namespaces |
| `util-linux` | | standard tools used by scripts |
| Recommended: `passt` or `slirp4netns` | | only if the lab network is enabled |
| Recommended: `fuse-overlayfs` | | rootless storage on older kernels |
| Python standard library | | sqlite3, json, pty, subprocess, logging |

Kernel requirements: cgroups v2 and unprivileged user namespaces (Ubuntu defaults).
Per user: a range in `/etc/subuid` and `/etc/subgid` (created by `useradd` on Ubuntu;
`install.sh` adds one if missing).

## Laboratory image (built from `lab/Containerfile`)

Base `docker.io/library/ubuntu:24.04` plus Ubuntu packages: systemd, sudo, man-db, manpages,
info, nano, vim-tiny, procps, psmisc, iproute2, iputils-ping, net-tools, bind9-dnsutils,
netcat-openbsd, curl, wget, openssh-server/client, cron, at, logrotate, acl, attr,
libcap2-bin, e2fsprogs, dosfstools, fdisk, parted, gdisk, lvm2, xfsprogs, fuse2fs, fuse3,
nftables, iptables, tar, gzip, bzip2, xz-utils, zip, unzip, rsync, bc, gawk, plocate,
lsof, strace, kmod, sysstat, quota, dpkg-dev, tmux, python3 (from the base system).
Offline repository: tree, sl, figlet, hello, jq (+libjq1, libonig5), ncdu, cowsay, htop.

Building the image needs Internet access to `docker.io` and `archive.ubuntu.com`;
importing a pre-built archive does not.

## Build and test

| Package | Purpose |
|---|---|
| `dpkg-dev` (dpkg-deb), `rsync` | building the .deb |
| `python3-pytest` | test suite |
| `xvfb` (optional) | visible-display GUI testing; tests use Qt's offscreen platform otherwise |
| `lxd` (optional) | clean-system deployment testing |
