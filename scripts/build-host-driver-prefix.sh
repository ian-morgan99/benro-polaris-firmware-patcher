#!/usr/bin/env bash
# Canonical host-side libgphoto2 driver prefix builder. ONE script, same flags every time.
#
# Why this exists: the Pentax capture path is behind the upstream containment guard
# LIBGPHOTO2_ENABLE_PENTAX_RESEARCH_CAPTURE (libgphoto2 fea32b59e "Contain unverified
# Pentax capture paths"). Shipping firmware always enables it via container/build_ptp2.sh.
# A host prefix built WITHOUT it does not merely lose the Pentax path: camera_capture()
# returns GP_ERROR_NOT_SUPPORTED (-6) as soon as vendor mode is enabled, before any
# standard PTP InitiateCapture attempt. That -6 looks exactly like a camera or driver
# defect and has already caused one misdiagnosis. So this script always enables the flag
# and then FAILS LOUDLY if the resulting binary does not contain the Pentax capture path.
#
# Usage:
#   scripts/build-host-driver-prefix.sh --pin <libgphoto2-sha> [--out <dir>] [--force]
#
# Defaults: pin = libgphoto2 origin/main, out = $POLARIS_OUT/v117-host-driver-prefix
set -euo pipefail

PATCHER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIBGPHOTO2_REPO="${LIBGPHOTO2_REPO:-$PATCHER_ROOT/../LibGphoto2/libgphoto2}"
OUT="${POLARIS_OUT:-/home/ian/polaris-v101/out}"

PIN=""
PREFIX=""
FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --pin)   PIN="$2"; shift 2;;
        --out)   PREFIX="$2"; shift 2;;
        --force) FORCE=1; shift;;
        -h|--help) sed -n '2,20p' "$0"; exit 0;;
        *) echo "unknown option: $1" >&2; exit 2;;
    esac
done

[ -d "$LIBGPHOTO2_REPO/.git" ] || { echo "libgphoto2 repo not found: $LIBGPHOTO2_REPO" >&2; exit 1; }
git -C "$LIBGPHOTO2_REPO" fetch -q origin main
PIN="${PIN:-$(git -C "$LIBGPHOTO2_REPO" rev-parse origin/main)}"
git -C "$LIBGPHOTO2_REPO" cat-file -e "${PIN}^{commit}" 2>/dev/null || { echo "no such commit: $PIN" >&2; exit 1; }
PIN="$(git -C "$LIBGPHOTO2_REPO" rev-parse "$PIN")"
[ -n "$PREFIX" ] || PREFIX="$OUT/v117-host-driver-prefix"

# These flags are the contract. Do not edit them ad hoc; change them here and nowhere else.
MESON_FLAGS=(
    --libdir=lib
    --wrap-mode=nodownload
    -Dcamlibs=ptp2,directory
    -Diolibs=libusb1,disk
    -Ddocs=false
    -Dpentax_research_capture=true
)

SRC="$OUT/.host-driver-src/${PIN:0:9}"

# Idempotent fast path: same pin, clean tree, markers present -> reuse.
PTP2="$PREFIX/lib/libgphoto2/2.5.34/ptp2.so"
if [ "$FORCE" != 1 ] && [ -f "$PTP2" ] && [ -f "$PREFIX/provenance.txt" ] \
   && grep -q "^pin=$PIN$" "$PREFIX/provenance.txt"; then
    if [ "$(grep -ac 'boundary=camlib-enter' "$PTP2")" = "1" ]; then
        echo "REUSE $PREFIX (pin=${PIN:0:9}, research capture present)"
        exit 0
    fi
fi

for t in meson ninja; do command -v "$t" >/dev/null || { echo "missing tool: $t" >&2; exit 1; }; done

# Self-contained clone, detached at the pin. A git worktree is not acceptable here: its
# .gitfile pointer does not resolve when only the source dir is mounted into a container.
if [ ! -d "$SRC/.git" ]; then
    mkdir -p "$(dirname "$SRC")"
    git clone -q "$LIBGPHOTO2_REPO" "$SRC"
fi
git -C "$SRC" fetch -q origin 2>/dev/null || true
git -C "$SRC" checkout -q --detach "$PIN"
[ -z "$(git -C "$SRC" status --porcelain)" ] || { echo "source tree dirty: $SRC" >&2; exit 1; }

BUILD="$OUT/.host-driver-build/${PIN:0:9}"
rm -rf "$BUILD" "$PREFIX"
echo "[build] pin=${PIN:0:9} flags: ${MESON_FLAGS[*]}"
meson setup "$BUILD" "$SRC" --prefix="$PREFIX" "${MESON_FLAGS[@]}" > "$OUT/.host-driver-build.log" 2>&1
ninja -C "$BUILD" -j"$(nproc)" >> "$OUT/.host-driver-build.log" 2>&1
meson install -C "$BUILD" >> "$OUT/.host-driver-build.log" 2>&1

# --- assertion: the Pentax capture path must be compiled in -------------------------
PTP2="$PREFIX/lib/libgphoto2/2.5.34/ptp2.so"
USB1="$(ls "$PREFIX"/lib/libgphoto2_port/*/usb1.so 2>/dev/null | head -1)"
[ -f "$PTP2" ] || { echo "FAIL: no ptp2.so at $PTP2 (log: $OUT/.host-driver-build.log)" >&2; exit 1; }
[ -n "$USB1" ] || { echo "FAIL: no usb1.so under $PREFIX/lib/libgphoto2_port" >&2; exit 1; }

# boundary=camlib-enter is the fprintf at the top of camera_pentax_capture_internal(),
# i.e. proof the research-capture branch was compiled rather than #ifndef'd out.
if [ "$(grep -ac 'boundary=camlib-enter' "$PTP2")" != "1" ]; then
    echo "FAIL: ptp2.so has no Pentax capture path. pentax_research_capture did not take." >&2
    echo "      A prefix built this way returns -6 on every capture and will be misread as a" >&2
    echo "      camera defect. Refusing to hand it to any test." >&2
    exit 1
fi
if [ "$(grep -ac 'pentax-capture\[' "$PTP2")" -lt 1 ]; then
    echo "FAIL: ptp2.so has no pentax-capture log instrumentation" >&2; exit 1
fi

{
    echo "pin=$PIN"
    echo "built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "meson_flags=${MESON_FLAGS[*]}"
    echo "ptp2_sha256=$(sha256sum "$PTP2" | cut -d' ' -f1)"
    echo "usb1_sha256=$(sha256sum "$USB1" | cut -d' ' -f1)"
} > "$PREFIX/provenance.txt"

echo "OK $PREFIX"
echo "   pin=${PIN:0:9}  ptp2=$(sha256sum "$PTP2" | cut -c1-16)  research-capture=verified"
echo "   export POLARIS_PENTAX_DRIVER_PREFIX=$PREFIX"
