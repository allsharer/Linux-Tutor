#!/bin/bash
# Linux Tutor - automated installation for Ubuntu.
#
# Usage (from an unpacked release bundle or a source checkout):
#     ./install.sh                     # install package + dependencies, then set up YOUR laboratory
#     ./install.sh --lab-image FILE    # use a pre-built laboratory image archive (offline)
#     ./install.sh --no-lab            # install the application only
#
# Run as your normal user; the script uses sudo for the system-wide steps.  The
# laboratory is per user (rootless Podman), so it is set up for the user running this.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
LAB_IMAGE=""
SETUP_LAB=1
while [ $# -gt 0 ]; do
    case "$1" in
        --lab-image) LAB_IMAGE=$(readlink -f "$2"); shift 2 ;;
        --no-lab) SETUP_LAB=0; shift ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "run this script as your normal user, not as root (sudo is used where needed)."
command -v sudo >/dev/null || fail "sudo is required."

say "Checking the system"
. /etc/os-release
echo "    $PRETTY_NAME, kernel $(uname -r)"
if [ "${ID:-}" != "ubuntu" ] && [[ " ${ID_LIKE:-} " != *" ubuntu "* ]] && [[ " ${ID_LIKE:-} " != *" debian "* ]]; then
    echo "    WARNING: Linux Tutor is designed for Ubuntu; continuing anyway."
fi
ver=${VERSION_ID%%.*}
if [ "${ID:-}" = "ubuntu" ] && [ "${ver:-0}" -lt 24 ]; then
    fail "Ubuntu 24.04 or newer is required (PySide6 packages)."
fi

# Locate the package: release bundle (dist/ or alongside) or build it from source.
DEB=$(ls -1 "$HERE"/linux-tutor_*_all.deb "$HERE"/../dist/linux-tutor_*_all.deb 2>/dev/null | sort -V | tail -1 || true)
if [ -z "$DEB" ]; then
    if [ -x "$HERE/build-deb.sh" ]; then
        say "Building the package from source"
        sudo apt-get install -y dpkg-dev rsync python3 >/dev/null
        "$HERE/build-deb.sh"
        DEB=$(ls -1 "$HERE"/../dist/linux-tutor_*_all.deb | sort -V | tail -1)
    else
        fail "no linux-tutor_*.deb found next to this script."
    fi
fi
echo "    package: $DEB"

say "Installing Linux Tutor and its dependencies (sudo)"
sudo apt-get update -qq
sudo apt-get install -y --reinstall "$DEB"

say "Checking rootless Podman for $(id -un)"
grep -q "^$(id -un):" /etc/subuid || { echo "    adding subordinate UID/GID ranges"; sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$(id -un)"; }
podman info --format '{{.Host.Security.Rootless}}' >/dev/null || fail "podman does not work for this user - see INSTALL.md (troubleshooting)."

if [ "$SETUP_LAB" -eq 1 ]; then
    if [ -n "$LAB_IMAGE" ]; then
        say "Importing the laboratory image from $LAB_IMAGE"
        linux-tutor-lab import "$LAB_IMAGE"
    elif ls "$HERE"/linux-tutor-lab-image*.tar* >/dev/null 2>&1; then
        img=$(ls -1 "$HERE"/linux-tutor-lab-image*.tar* | tail -1)
        say "Importing the bundled laboratory image $img"
        linux-tutor-lab import "$img"
    else
        say "Building the laboratory image (downloads Ubuntu packages; several minutes)"
        linux-tutor-lab build
    fi
    say "Verifying the installation"
    linux-tutor-lab check
fi

say "Done.  Start Linux Tutor from your applications menu, or run:  linux-tutor"
