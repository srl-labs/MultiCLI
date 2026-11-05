#!/bin/bash
###############################################################################
# build-deb.sh
# MultiCLI NDK Agent Debian Package Builder
# Builds Debian Policy (§5.6.1) packages: srl-multicli_<version>_<arch>.deb
# Usage: ./ndk-agent/build-deb.sh [amd64|arm64|all]
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ARCH="${1:-all}"
VERSION="${VERSION:-0.2.0}"

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "Error: dpkg-deb is required to build Debian packages."
    exit 1
fi

ARCH_LIST=()
case "$TARGET_ARCH" in
    all)
        ARCH_LIST=("amd64" "arm64")
        ;;
    amd64|arm64)
        ARCH_LIST=("$TARGET_ARCH")
        ;;
    *)
        echo "Usage: $0 [amd64|arm64|all]"
        exit 1
        ;;
esac

for ARCH in "${ARCH_LIST[@]}"; do
    PKG_FILE="srl-multicli_${VERSION}_${ARCH}.deb"
    echo "==> Building ${PKG_FILE}..."
    BUILD_ROOT="$(mktemp -d "/tmp/multicli-build-${ARCH}-XXXXXX")"
    trap 'rm -rf "$BUILD_ROOT"' EXIT

    cp -r "$SCRIPT_DIR/src/." "$BUILD_ROOT/"

    find "$BUILD_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$BUILD_ROOT" -type f -name "*.py[cod]" -delete 2>/dev/null || true

    find "$BUILD_ROOT" -type d -exec chmod 755 {} +
    find "$BUILD_ROOT/DEBIAN" -type f -exec chmod 644 {} +
    find "$BUILD_ROOT/etc" -type f -exec chmod 644 {} +
    chmod 755 "$BUILD_ROOT/etc/opt/srlinux/appmgr/multicli/multicli.py"
    chmod 755 "$BUILD_ROOT/etc/opt/srlinux/appmgr/multicli/multicli.sh"
    chmod 755 "$BUILD_ROOT/etc/opt/srlinux/appmgr/multicli/multicli_version.sh"

    printf '#!/bin/bash\n\necho "v%s"\n' "${VERSION}" > "$BUILD_ROOT/etc/opt/srlinux/appmgr/multicli/multicli_version.sh"
    chmod 755 "$BUILD_ROOT/etc/opt/srlinux/appmgr/multicli/multicli_version.sh"

    INSTALLED_KB="$(du -sk "$BUILD_ROOT/etc" | awk '{print $1}')"
    sed -i "s/^Architecture: .*/Architecture: ${ARCH}/" "$BUILD_ROOT/DEBIAN/control"
    sed -i "s/^Version: .*/Version: ${VERSION}/" "$BUILD_ROOT/DEBIAN/control"
    sed -i "s/^Installed-Size: .*/Installed-Size: ${INSTALLED_KB}/" "$BUILD_ROOT/DEBIAN/control"

    (
        cd "$BUILD_ROOT"
        find etc -type f -exec md5sum {} + | sort -k 2 > "$BUILD_ROOT/DEBIAN/md5sums"
        chmod 644 "$BUILD_ROOT/DEBIAN/md5sums"
    )

    OUTPUT_DEB="$SCRIPT_DIR/${PKG_FILE}"
    dpkg-deb -Zgzip --build --root-owner-group "$BUILD_ROOT" "$OUTPUT_DEB" >/dev/null

    echo "==> Generated: $OUTPUT_DEB ($(ls -lh "$OUTPUT_DEB" | awk '{print $5}'))"
    rm -rf "$BUILD_ROOT"
    trap - EXIT
done

echo "==> Build complete for [${ARCH_LIST[*]}]."
