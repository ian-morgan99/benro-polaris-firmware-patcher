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
# The build compiles whatever is checked out in this directory, so it must be a
# tree sitting exactly on the pin. The developer's own driver checkout is routinely
# dirty and on another branch -- pointing the build at it either fails with "wrong
# libgphoto2 commit" or silently compiles something else.
#
# This must be a real clone, NOT a git worktree. container/build_ptp2.sh runs
#   git -C /libgphoto2-source-input rev-parse --is-inside-work-tree
# and only $LIBSRC is mounted into the container. A worktree's .git is a one-line
# file pointing at $LIB_REPO/.git/worktrees/<name>, which lives outside that
# mount, so inside the container the repository is unresolvable and the build dies
# with "local source directory must be a Git checkout". A clone carries its own
# .git directory inside the mounted path and works.
LIB_REPO="/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2"
LIBSRC="${POLARIS_V96_LIBSRC:-$ROOT/out/.libgphoto2-v96}"
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
[ -f "$SUMMARY" ]  || die "change summary missing: $SUMMARY"

LIB_PIN="$(sed -n 's/^LIB_BASELINE="\([0-9a-f]\{40\}\)".*/\1/p' "$ROOT/scripts/build-astro-candidate.sh" | head -1)"
[ -n "$LIB_PIN" ] || die "could not read LIB_BASELINE from scripts/build-astro-candidate.sh"

# Provision the pinned source on demand. A local clone shares objects with
# $LIB_REPO, so it is cheap; --no-checkout then a detached checkout of the exact
# pin keeps HEAD precisely where the recorded provenance says it should be.
if [ ! -d "$LIBSRC/.git" ]; then
    [ -d "$LIB_REPO/.git" ] || die "driver repo missing: $LIB_REPO"
    if [ -e "$LIBSRC" ] && [ ! -d "$LIBSRC/.git" ]; then
        die "$LIBSRC exists but is not a git clone (a worktree will not work here -- see comment above)"
    fi
    echo "== cloning pinned driver source into $LIBSRC at ${LIB_PIN:0:9} =="
    git clone --no-checkout --local "$LIB_REPO" "$LIBSRC" \
      || die "could not clone $LIB_REPO into $LIBSRC"
    git -C "$LIBSRC" checkout --detach "$LIB_PIN" >/dev/null 2>&1 \
      || die "pin $LIB_PIN is not present in $LIB_REPO (run: git -C $LIB_REPO fetch)"
elif [ ! -e "$LIBSRC" ]; then
    die "libgphoto2 source missing and cannot be created: $LIBSRC"
fi

# A worktree left over from an earlier run looks like a checkout to every check
# below but still fails inside the container. Catch it here, where the reason is
# obvious, rather than 40 minutes into the build.
if [ -f "$LIBSRC/.git" ]; then
    echo "ERROR: $LIBSRC is a git worktree (.git is a file, not a directory)."
    echo "       The container only mounts this directory, so its repository lives"
    echo "       outside the mount and build_ptp2.sh cannot resolve it."
    echo "       Remove it and re-run to get a self-contained clone:"
    echo "         rm -rf $LIBSRC"
    exit 1
fi

[ "$(git -C "$LIBSRC" rev-parse HEAD)" = "$LIB_PIN" ] \
  || die "source $LIBSRC is at $(git -C "$LIBSRC" rev-parse HEAD), not the pin $LIB_PIN"
git -C "$LIBSRC" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "source $LIBSRC is not a usable git checkout"
if [ -n "$(git -C "$LIBSRC" status --porcelain --untracked-files=all)" ]; then
    echo "ERROR: pinned source $LIBSRC is dirty. The build compiles what is on disk,"
    echo "       so a dirty tree produces a candidate that does not match its recorded pin."
    echo "       Clean it (git -C $LIBSRC status) or point POLARIS_V96_LIBSRC elsewhere."
    exit 1
fi
echo "== libgphoto2 source: $LIBSRC at ${LIB_PIN:0:9} (clean, self-contained clone) =="

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
    echo "== docker daemon not answering; trying to start it =="
    # The desktop launcher runs in a real terminal, so sudo can prompt there.
    # Only attempt this under systemd; a container or non-systemd host has no
    # systemctl and would just print a confusing second error.
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl start docker || echo "   (sudo systemctl start docker failed)"
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            "$DOCKER_BIN" info >/dev/null 2>&1 && break
            sleep 1
        done
    fi
    if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
        echo "ERROR: the Docker daemon is still not answering."
        echo "       $("$DOCKER_BIN" info 2>&1 | head -2 | tr '\n' ' ')"
        echo "       Start it yourself and re-run:  sudo systemctl start docker"
        exit 1
    fi
fi
echo "== docker daemon: $("$DOCKER_BIN" info --format '{{.ServerVersion}}' 2>/dev/null || echo unknown) =="

# The pin gate that would have caught v95. Run here so it cannot be skipped by
# forgetting a flag; build-astro-candidate.sh runs it too, but only when the pin
# differs from its default. LIB_PIN was read once above, when the worktree was
# provisioned.
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

# Not exec: the exit code alone is not enough to say whether a candidate exists.
# A build can fail after writing partial output, and "it closed quickly" then
# leaves no way to tell success from failure. Verify the artifacts themselves.
bash "$ROOT/scripts/build-astro-candidate.sh" \
  --id "$CANDIDATE_ID" \
  --stock-fwpkt "$STOCK" \
  --libgphoto2-source "$LIBSRC" \
  --display-fwver "$DISPLAY_FWVER" \
  --build-id "$CANDIDATE_ID" \
  --catalog-package "$CATALOG" \
  --change-summary "$SUMMARY" \
  --out "$OUT"
rc=$?

echo "============================================================"
if [ "$rc" -eq 0 ] && [ -s "$OUT/FwPkt.zip" ] && [ -s "$OUT/astro-candidate-manifest.json" ]; then
    echo "BUILD SUCCEEDED: $CANDIDATE_ID ($DISPLAY_FWVER)"
    echo "  FwPkt.zip  $(sha256sum "$OUT/FwPkt.zip" | cut -c1-64)"
    echo "  size       $(stat -c %s "$OUT/FwPkt.zip") bytes"
    echo "  manifest   $OUT/astro-candidate-manifest.json"
    echo "  log        ${LOG:-none}"
    echo
    echo "NOT INSTALLED. Nothing was staged, flashed or uploaded."
    echo "Physical qualification on a real camera is still required."
else
    echo "BUILD FAILED (exit $rc)"
    [ -s "$OUT/FwPkt.zip" ] && echo "  WARNING: a partial FwPkt.zip exists -- do not use it" || echo "  no FwPkt.zip produced"
    echo "  log        ${LOG:-none}"
    echo "  last lines of the log:"
    [ -n "${LOG:-}" ] && [ -f "$LOG" ] && tail -25 "$LOG" | sed 's/^/    /'
fi
echo "============================================================"
exit "$rc"
