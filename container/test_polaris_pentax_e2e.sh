#!/bin/bash
# End-to-end Pentax->Polaris build regression.
#
# Validates the entire consolidation: a clean upstream libgphoto2 git checkout
# is mounted into the patcher container, the cross-build runs, the Pentax
# marker is present in ptp2.so, the firmware bundle is produced, the stage-2
# on-disk bundle is present, and the stage-2 loader compiles with the same
# cross-toolchain.
#
# This is a NO-EMULATION smoke test: it does not need a Polaris gimbal or a
# Pentax camera, only the patched toolchain + the local libgphoto2 source.
#
# Usage:
#   test_polaris_pentax_e2e.sh IMAGE FW_PKT_DIR CLEAN_LIBGPHOTO2_GIT_CHECKOUT

set -euo pipefail

IMAGE="${1:-polaris-patcher-fixed}"
FW_PKT="${2:-}"
SOURCE="${3:-}"
[ -n "$FW_PKT" ] && [ -n "$SOURCE" ] && [ -f "$SOURCE/configure.ac" ] || {
  echo "usage: $0 DOCKER_IMAGE FW_PKT_DIR CLEAN_LIBGPHOTO2_GIT_CHECKOUT" >&2
  exit 2
}

# FW_PKT must be a directory whose direct children include firmwareInfo
# (the patcher looks for /in/firmwareInfo inside the container).
[ -f "$FW_PKT/firmwareInfo" ] || {
  echo "FW_PKT_DIR must contain firmwareInfo directly (got: $FW_PKT)" >&2
  exit 2
}

T="$(mktemp -d)"
cleanup() {
  docker rm -f polaris-pentax-e2e >/dev/null 2>&1 || true
  find "$T" -depth -mindepth 1 -delete 2>/dev/null || true
  rmdir "$T" 2>/dev/null || true
  return 0
}
trap cleanup EXIT

# 1) Drive the end-to-end build in the fixed image. We use MODE=full so we
#    exercise the firmware packaging path; ALLOW_DIRTY_SOURCE=0 enforces
#    the clean-checkout requirement. Pentax profile is the consolidation
#    target.
if ! docker run --rm --name polaris-pentax-e2e \
  -e MODE=full \
  -e LIBGPHOTO2_VERSION=2.5.34 \
  -e FIX_R5M2_TYPO=1 \
  -e SELFTEST=0 \
  -e SWAP_USB1=1 \
  -e ALLOW_DIRTY_SOURCE=0 \
  -e PENTAX=1 \
  -v "$SOURCE:/libgphoto2-source-input:ro" \
  -v "$FW_PKT:/in:ro" \
  -v "$T:/out" \
  "$IMAGE" > "$T/build.log" 2>&1; then
  echo "docker run failed; last 40 log lines:" >&2
  tail -40 "$T/build.log" >&2
  exit 1
fi

# 2) Source provenance is recorded.
[ -f "$T/build-source-provenance.txt" ] || { echo "missing build-source-provenance.txt" >&2; exit 1; }
test "$(sed -n 's/^actual_version=//p' "$T/build-source-provenance.txt")" = 2.5.34
EXPECTED_SHA="$(git -C "$SOURCE" rev-parse HEAD)"
ACTUAL_SHA="$(sed -n 's/^git_commit=//p' "$T/build-source-provenance.txt")"
test "$ACTUAL_SHA" = "$EXPECTED_SHA" || {
  echo "source SHA mismatch: build=$ACTUAL_SHA source=$EXPECTED_SHA" >&2; exit 1; }
test -z "$(sed -n 's/^dirty_diff_hash=//p' "$T/build-source-provenance.txt")" || {
  echo "dirty source was not rejected" >&2; exit 1; }

# 3) Firmware bundle is rebuilt (these are the FwPkt files the patcher ships).
[ -f "$T/FwPkt.zip" ] || { echo "missing FwPkt.zip" >&2; exit 1; }
[ -f "$T/FwPkt/camera/appfs.ubifs" ] || { echo "missing FwPkt/camera/appfs.ubifs" >&2; exit 1; }
[ -f "$T/FwPkt/camera/rootfs.ubifs" ] || { echo "missing FwPkt/camera/rootfs.ubifs" >&2; exit 1; }
[ -f "$T/FwPkt/camera/uImage" ] || { echo "missing FwPkt/camera/uImage" >&2; exit 1; }
[ -f "$T/FwPkt/firmwareInfo" ] || { echo "missing FwPkt/firmwareInfo" >&2; exit 1; }
[ -d "$T/FwPkt/gimbal" ] || { echo "missing FwPkt/gimbal" >&2; exit 1; }

# 4) The patcher's two Pentax gates both passed in the build log.
grep -q 'local-source Pentax candidate marker: present' "$T/build.log" || {
  echo "Pentax marker gate failed" >&2; tail -40 "$T/build.log" >&2; exit 1; }
grep -q 'K-01 model string present' "$T/build.log" || {
  echo "PENTAX=1 K-01 model gate failed" >&2; tail -40 "$T/build.log" >&2; exit 1; }

# 5) The on-disk stage-2 bundle is shipped.
[ -f "$T/stage2-ondisk/ondisk/install_stage2.sh" ] || { echo "missing install_stage2.sh" >&2; exit 1; }
[ -f "$T/stage2-ondisk/ondisk/restore_stock.sh" ] || { echo "missing restore_stock.sh" >&2; exit 1; }
[ -f "$T/stage2-ondisk/ondisk/libpolaris_stage2.so" ] || { echo "missing libpolaris_stage2.so" >&2; exit 1; }

# 6) The on-disk ptp2 is the freshly-cross-built 2.5.34 with Pentax marker.
PTP2_SO="$T/stage2-ondisk/libgphoto2/2.5.34/ptp2.so"
[ -f "$PTP2_SO" ] || { echo "missing on-disk ptp2 ($PTP2_SO)" >&2; exit 1; }
# Use grep -F (no -q) and capture in a temp file to avoid the
# set -euo pipefail + grep -q SIGPIPE issue documented in
# BenroPolarisPatcher/docs/pentax-patcher-gate-bug.md.
PTP2_MARKER_FILE="$(mktemp)"
strings "$PTP2_SO" > "$PTP2_MARKER_FILE" || true
grep -F 'Pentax vendor mode enabled' "$PTP2_MARKER_FILE" >/dev/null || {
  echo "Pentax vendor mode marker not in on-disk ptp2" >&2; rm -f "$PTP2_MARKER_FILE"; exit 1; }
rm -f "$PTP2_MARKER_FILE"
# And the trampolined on-disk core binary is shipped.
[ -f "$T/stage2-ondisk/libgphoto2.so.6" ] || { echo "missing on-disk libgphoto2.so.6" >&2; exit 1; }

# 7) The stage-2 loader compiles with the same cross-toolchain the image uses.
#    The generated slot table (stage2_ondisk_table.h) and stage2_policy.h
#    both ship with the image at /opt/patcher/, so no source mount is needed.
docker run --rm --entrypoint bash \
  "$IMAGE" -c '
    set -e
    arm-linux-gnueabi-gcc -shared -fPIC -O2 -Wall -Wextra -Werror -mfloat-abi=soft \
      -I/opt/patcher \
      -I/opt/patcher/testdata \
      -o /tmp/libpolaris_stage2.so \
      /opt/patcher/stage2_loader.c
    test -f /tmp/libpolaris_stage2.so
    file /tmp/libpolaris_stage2.so | grep -q "ARM"
  ' || { echo "stage-2 loader failed to compile" >&2; exit 1; }

echo "polaris-pentax end-to-end: PASS"
