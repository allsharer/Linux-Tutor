#!/bin/bash
# Build the Debian package dist/linux-tutor_<version>_all.deb from the source tree.
#
#   scripts/build-deb.sh            # build
#   scripts/build-deb.sh --test     # build, then run the unit tests and lint the package
#
# Requirements: dpkg-deb (package dpkg), python3.  No root privileges needed.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(python3 -c "import re,sys; print(re.search(r'__version__ = \"([^\"]+)\"', open('$ROOT/linux_tutor/__init__.py').read()).group(1))")
PKG=linux-tutor
STAGE="$ROOT/build/deb/${PKG}_${VERSION}_all"
DIST="$ROOT/dist"

echo "Building $PKG $VERSION"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/$PKG" "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" "$STAGE/usr/share/doc/$PKG" "$STAGE/etc/$PKG" "$DIST"

# Application code, curriculum and laboratory build files (architecture-independent data).
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/linux_tutor" "$STAGE/usr/share/$PKG/"
rsync -a "$ROOT/curriculum" "$STAGE/usr/share/$PKG/"
rsync -a "$ROOT/lab" "$STAGE/usr/share/$PKG/"
install -m 755 "$ROOT/packaging/bin/linux-tutor" "$ROOT/packaging/bin/linux-tutor-lab" "$STAGE/usr/bin/"
install -m 644 "$ROOT/packaging/desktop/linux-tutor.desktop" "$STAGE/usr/share/applications/"
install -m 644 "$ROOT/packaging/desktop/linux-tutor.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "$ROOT/packaging/config.json" "$STAGE/etc/$PKG/config.json"
for d in README.md INSTALL.md UNINSTALL.md SECURITY.md CURRICULUM.md ASSESSMENT.md BACKUP-RESTORE.md DEPENDENCIES.md CHANGELOG.md LICENSE; do
    [ -f "$ROOT/$d" ] && install -m 644 "$ROOT/$d" "$STAGE/usr/share/doc/$PKG/"
done

# Byte-compile check (fails the build on syntax errors).
python3 -m compileall -q "$STAGE/usr/share/$PKG/linux_tutor" >/dev/null
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +

SIZE=$(du -sk "$STAGE" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" "$ROOT/packaging/debian/control.in" > "$STAGE/DEBIAN/control"
install -m 755 "$ROOT/packaging/debian/postinst" "$ROOT/packaging/debian/postrm" "$STAGE/DEBIAN/"
echo "/etc/$PKG/config.json" > "$STAGE/DEBIAN/conffiles"
(cd "$STAGE" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' | sort -z | xargs -0 md5sum) > "$STAGE/DEBIAN/md5sums"

find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE/usr/share" "$STAGE/etc" -type f -exec chmod 644 {} +
OUT="$DIST/${PKG}_${VERSION}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"

if [ "${1:-}" = "--test" ]; then
    dpkg-deb --info "$OUT" | sed -n '1,25p'
    command -v lintian >/dev/null && lintian --no-tag-display-limit "$OUT" || true
    (cd "$ROOT" && LINUX_TUTOR_SKIP_LAB=1 python3 -m pytest -q -m "not lab")
fi
