#!/bin/bash
# Produce a self-contained release bundle in dist/:
#
#   dist/linux-tutor-<version>/
#       linux-tutor_<version>_all.deb
#       linux-tutor-lab-image-<labversion>.tar.gz   (optional, --with-image; allows offline install)
#       install.sh  uninstall.sh  *.md
#   dist/linux-tutor-<version>.tar.gz
#
# The laboratory image is exported from THIS machine's rootless Podman storage
# (build it first with: linux-tutor-lab build, or python3 -m linux_tutor.cli build).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WITH_IMAGE=0
[ "${1:-}" = "--with-image" ] && WITH_IMAGE=1

"$ROOT/scripts/build-deb.sh"
VERSION=$(python3 -c "import re; print(re.search(r'__version__ = \"([^\"]+)\"', open('$ROOT/linux_tutor/__init__.py').read()).group(1))")
LABV=$(python3 -c "import re; print(re.search(r'LAB_IMAGE_VERSION = \"([^\"]+)\"', open('$ROOT/linux_tutor/lab/__init__.py').read()).group(1))")
OUT="$ROOT/dist/linux-tutor-$VERSION"
rm -rf "$OUT"; mkdir -p "$OUT"
cp "$ROOT/dist/linux-tutor_${VERSION}_all.deb" "$OUT/"
cp "$ROOT/scripts/install.sh" "$ROOT/scripts/uninstall.sh" "$OUT/"
for d in README.md INSTALL.md UNINSTALL.md DEPLOYMENT.md DEPENDENCIES.md BACKUP-RESTORE.md SECURITY.md CHANGELOG.md; do
    [ -f "$ROOT/$d" ] && cp "$ROOT/$d" "$OUT/"
done
if [ "$WITH_IMAGE" -eq 1 ]; then
    CACHE="$ROOT/dist/linux-tutor-lab-image-$LABV.tar.gz"
    IMGID=$(podman image inspect --format '{{.Id}}' "localhost/linux-tutor-lab:$LABV")
    if [ ! -f "$CACHE" ] || [ "$(cat "$CACHE.id" 2>/dev/null)" != "$IMGID" ]; then
        echo "Exporting laboratory image localhost/linux-tutor-lab:$LABV ..."
        podman save --format oci-archive -o "${CACHE%.gz}" "localhost/linux-tutor-lab:$LABV"
        gzip -1 -f "${CACHE%.gz}" && echo "$IMGID" > "$CACHE.id"
    fi
    cp "$CACHE" "$OUT/"
fi
(cd "$OUT" && sha256sum -- * > SHA256SUMS)
tar czf "$ROOT/dist/linux-tutor-$VERSION.tar.gz" -C "$ROOT/dist" "linux-tutor-$VERSION"
echo "Release bundle: $ROOT/dist/linux-tutor-$VERSION.tar.gz"
ls -lh "$OUT"
