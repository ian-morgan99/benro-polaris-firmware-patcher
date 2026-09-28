#!/usr/bin/env bash
# Build, gate, fingerprint, and privately publish one reproducible candidate.
# This is the only supported source-to-candidate entry point for normal work.
set -euo pipefail

usage() {
  echo "usage: $0 <id> <stock-FwPkt.zip|dir> <clean-libgphoto2-checkout> [build-id] [display-fwver]" >&2
  exit 2
}
[ $# -ge 3 ] && [ $# -le 5 ] || usage
ID="$1"; BASE="$2"; SRC="$3"; BUILD_ID="${4:-$ID}"; DISPLAY_FWVER="${5:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/$ID"

case "$ID" in (*[!a-zA-Z0-9._-]*) echo "ERROR: invalid candidate id" >&2; exit 2;; esac
[ -e "$BASE" ] || { echo "ERROR: stock FwPkt not found: $BASE" >&2; exit 2; }
[ -d "$SRC/.git" ] || { echo "ERROR: libgphoto2 input must have a real .git directory" >&2; exit 2; }
[ "$(git -C "$SRC" status --porcelain)" = "" ] || { echo "ERROR: libgphoto2 checkout is dirty" >&2; exit 2; }
BRANCH="$(git -C "$SRC" branch --show-current)"
[ "$BRANCH" = main ] || { echo "ERROR: libgphoto2 must be on main (got ${BRANCH:-detached})" >&2; exit 2; }
SRC_SHA="$(git -C "$SRC" rev-parse HEAD)"
echo "Building $ID from libgphoto2 main $SRC_SHA and stock base $BASE"

command -v meson >/dev/null || { echo "ERROR: meson is required for libgphoto2 regression tests" >&2; exit 2; }
TEST_BUILD="$(mktemp -d "${TMPDIR:-/tmp}/libgphoto2-regression.XXXXXX")"
trap 'rm -rf "$TEST_BUILD"' EXIT
echo "Running libgphoto2 deterministic regression pack"
meson setup "$TEST_BUILD" "$SRC" --buildtype=debugoptimized -Dcamlibs=ptp2,pentax,directory >/dev/null
meson compile -C "$TEST_BUILD"
echo "SKIP: libgphoto2:test-gp-port (no-ci serial control-line test; host has no supported DTR/CTS fixture)"
meson test -C "$TEST_BUILD" --no-suite no-ci --print-errorlogs

PATCH_ARGS=(--fwpkt "$(realpath "$BASE")" \
  --libgphoto2-source "$(realpath "$SRC")" --out "$OUT" --build-id "$BUILD_ID")
if [ -n "$DISPLAY_FWVER" ]; then
  PATCH_ARGS+=(--display-fwver "$DISPLAY_FWVER")
fi
"$ROOT/patch-polaris.sh" "${PATCH_ARGS[@]}"
"$ROOT/tests/run_prerelease_gate.sh" --build "$OUT/FwPkt"
bash "$ROOT/.github/skills/fwpkt-private-upload/scripts/upload-fwpkt-to-pr.sh" \
  --build "$OUT" --id "$ID" --status candidate \
  --note "Main-branch reproducible candidate; gate passed; physical test pending."
echo "Candidate ready: $OUT/FwPkt.zip"
md5sum "$OUT/FwPkt.zip"; sha256sum "$OUT/FwPkt.zip"
