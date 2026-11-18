#!/bin/bash
# Linux Tutor - uninstall.
#
#     ./uninstall.sh              # remove the application; KEEP student records and laboratory
#     ./uninstall.sh --lab        # also remove YOUR laboratory containers and image
#     ./uninstall.sh --purge-data # also delete YOUR student records and settings (asks first)
set -euo pipefail
REMOVE_LAB=0; PURGE=0
for a in "$@"; do
    case "$a" in
        --lab) REMOVE_LAB=1 ;;
        --purge-data) PURGE=1; REMOVE_LAB=1 ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "unknown option $a" >&2; exit 2 ;;
    esac
done

if [ "$REMOVE_LAB" -eq 1 ] && command -v podman >/dev/null; then
    echo "Removing laboratory containers and images of $(id -un)..."
    if command -v linux-tutor-lab >/dev/null; then linux-tutor-lab remove-all || true; fi
    podman ps -a --filter label=org.linuxtutor.managed=true -q | xargs -r podman rm -f >/dev/null || true
    podman images --format '{{.Repository}}:{{.Tag}}' | grep '^localhost/linux-tutor-lab:' | xargs -r podman rmi -f || true
fi

if dpkg -s linux-tutor >/dev/null 2>&1; then
    echo "Removing the linux-tutor package (sudo)..."
    sudo apt-get purge -y linux-tutor
fi

if [ "$PURGE" -eq 1 ]; then
    data="${XDG_DATA_HOME:-$HOME/.local/share}/linux-tutor"
    conf="${XDG_CONFIG_HOME:-$HOME/.config}/linux-tutor"
    state="${XDG_STATE_HOME:-$HOME/.local/state}/linux-tutor"
    cache="${XDG_CACHE_HOME:-$HOME/.cache}/linux-tutor"
    echo "This permanently deletes your Linux Tutor profiles, scores and settings:"
    echo "  $data $conf $state $cache"
    read -r -p "Type DELETE to confirm: " answer
    if [ "$answer" = "DELETE" ]; then
        rm -rf "$data" "$conf" "$state" "$cache"
        echo "Student data deleted."
    else
        echo "Student data kept."
    fi
else
    echo "Student records were kept in ${XDG_DATA_HOME:-$HOME/.local/share}/linux-tutor"
fi
echo "Linux Tutor has been uninstalled."
