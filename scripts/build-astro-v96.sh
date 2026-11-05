#!/usr/bin/env bash
# Build the astro-v96 candidate. One command, no arguments, fixed paths.
#
# Why this file exists: v95 was built from an ad-hoc tree (/home/ian/v95-build)
# with its arguments typed by hand, and it pinned 855f718e5 -- the tip of
# feature/polaris-capture-events -- which turned out to be a regression, not an
# upgrade. That commit branched off driver main at 83240b36a on 2026-10-28 and
# never took 15 commits main gained afterwards, 9 of them touching shipped code,
# including 4fba11d81 "fix Pentax deferred Bulb cancellation". So v95 shipped
# without the #251 guard it was meant to carry.
#
# Every input below is absolute and was verified to exist. The driver pin is the
# script default (driver main, 3fb26e536), which scripts/pin-divergence-check.sh
# confirms is a clean superset of both the v95 pin and the v94 pin. Nothing here
# needs re-typing, and nothing creates a new working directory.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

CANDIDATE_ID="astro-v96-cancel-writer-20261105"
DISPLAY_FWVER="6.0.0.54.96"
STOCK="/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/firmware/FwPkt.zip"
CATALOG="/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/out/gaia-dr3-g10"
LIBSRC="/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2"
SUMMARY="$ROOT/docs/candidate-summaries/v96-astro-cancel-writer.json"
OUT="$ROOT/out/$CANDIDATE_ID"

# The stock input v95 was built from. If this digest changes, the candidate is
# not comparable to v95 and the operator should say so deliberately.
STOCK_SHA256="f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f"

die() { echo "ERROR: $*" >&2; exit 1; }

# Always leave a readable record. A Terminal=true launcher closes the window the
# moment this script exits, so an early failure -- most often "the Docker daemon
# is not answering" -- looked like the icon doing nothing at all.
LOG_DIR="${POLARIS_BUILD_LOG_DIR:-$HOME/.local/state/polaris-builds}"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="/tmp/polaris-builds"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG="${POLARIS_BUILD_LOG:-$LOG_DIR/astro-v96-$(date +%Y%m%d-%H%M%S).log}"

# Re-exec once under a tee pipeline rather than using process substitution.
# "exec > >(tee ...)" lets the script exit while tee is still buffering, which
# truncates exactly the trailing lines that explain a failure. POLARIS_BUILD_LOGGED
# stops the re-exec from looping.
if [ -z "${POLARIS_BUILD_LOGGED:-}" ] && { [ ! -e "${LOG%/*}" ] || [ -w "${LOG%/*}" ]; }; then
    echo "== log: $LOG =="
    POLARIS_BUILD_LOGGED=1 POLARIS_BUILD_LOG="$LOG" "$0" "$@" 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    if [ "$rc" -ne 0 ]; then
        echo "FAILED (exit $rc). Full log: $LOG"
        # The desktop launcher sets this so the window stays open long enough to
        # read the error. Never wait on a plain terminal or in CI.
        if [ "${POLARIS_BUILD_HOLD:-0}" = "1" ]; then
            printf '\nPress Enter to close this window... '
            read -r _ || true
        fi
    fi
    exit "$rc"
fi

[ -f "$STOCK" ]    || die "stock FwPkt missing: $STOCK"
[ -d "$CATALOG" ]  || die "catalogue package missing: $CATALOG"
[ -d "$LIBSRC" ]   || die "libgphoto2 source missing: $LIBSRC"
[ -f "$SUMMARY" ]  || die "change summary missing: $SUMMARY"

ACTUAL="$(sha256sum "$STOCK" | cut -d' ' -f1)"
[ "$ACTUAL" = "$STOCK_SHA256" ] || die "stock digest changed: expected $STOCK_SHA256 got $ACTUAL"

DOCKER_BIN="$(command -v docker 2>/dev/null || true)"
[ -n "$DOCKER_BIN" ] || DOCKER_BIN="$(command -v /run/host/usr/bin/docker 2>/dev/null || true)"
if [ -z "$DOCKER_BIN" ]; then
    echo "ERROR: no docker binary found. PATH=$PATH"
    exit 1
fi
# Put the located binary on PATH as well. scripts/build-astro-candidate.sh and
# the container build it drives call plain "docker", so resolving it only for
# this script's own checks would still fail later, further into the run.
DOCKER_DIR="$(dirname "$DOCKER_BIN")"
case ":$PATH:" in (*":$DOCKER_DIR:"*) ;; (*) PATH="$DOCKER_DIR:$PATH"; export PATH;; esac
echo "== docker binary: $DOCKER_BIN =="

if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
    echo "ERROR: the Docker daemon is not answering."
    echo "       $("$DOCKER_BIN" info 2>&1 | head -2 | tr '\n' ' ')"
    echo "       Start it, or run this from a normal desktop terminal session."
    exit 1
fi
echo "== docker daemon: $("$DOCKER_BIN" info --format '{{.ServerVersion}}' 2>/dev/null || echo unknown) =="

# The pin gate that would have caught v95. Run here so it cannot be skipped by
# forgetting a flag; build-astro-candidate.sh runs it too, but only when the pin
# differs from its default.
LIB_PIN="$(git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1 && \
           sed -n 's/^LIB_BASELINE="\([0-9a-f]\{40\}\)".*/\1/p' "$ROOT/scripts/build-astro-candidate.sh" | head -1)"
[ -n "$LIB_PIN" ] || die "could not read LIB_BASELINE from scripts/build-astro-candidate.sh"
bash "$ROOT/scripts/pin-divergence-check.sh" "$LIBSRC" "$LIB_PIN" \
     43dccb81b92b6b25f44957a4684f534393562028 \
  || die "driver pin $LIB_PIN is not a clean superset of the v94 pin -- refusing to build"

# The #251 guard must be present in the tree we are about to compile.
git -C "$LIBSRC" merge-base --is-ancestor 4fba11d81d948dd32520177e72ba266d3e444595 "$LIB_PIN" \
  || die "driver pin $LIB_PIN does not contain 4fba11d81 (deferred Bulb cancellation) -- this is the v95 mistake"

echo "== building $CANDIDATE_ID ($DISPLAY_FWVER) from $ROOT =="
echo "== driver pin $LIB_PIN (contains the #251 guard) =="
echo "== patcher commit $(git -C "$ROOT" rev-parse HEAD) =="
echo "== output $OUT =="

exec bash "$ROOT/scripts/build-astro-candidate.sh" \
  --id "$CANDIDATE_ID" \
  --stock-fwpkt "$STOCK" \
  --libgphoto2-source "$LIBSRC" \
  --display-fwver "$DISPLAY_FWVER" \
  --build-id "$CANDIDATE_ID" \
  --catalog-package "$CATALOG" \
  --change-summary "$SUMMARY" \
  --out "$OUT"
