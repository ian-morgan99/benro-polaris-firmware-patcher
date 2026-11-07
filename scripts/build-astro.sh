#!/usr/bin/env bash
# build-astro.sh -- build an Astro plate-solving candidate with ONE command.
#
#   scripts/build-astro.sh --version 98 --summary docs/release-change-summary-v98-astro.json
#
# WHY THIS EXISTS
# scripts/build-astro-candidate.sh is the real builder, but it needs nine flags and
# six environment prerequisites that nothing documents. On 2026-11-06 building v97
# took six failed attempts to get right, and every failure reported itself as
# something unrelated:
#
#   docker not found            -> the shell was in a Flatpak sandbox with no socket
#   /in/firmwareInfo not found  -> mktemp honoured a sandbox-private TMPDIR, so the
#                                  Docker bind mount came up EMPTY
#   must be a Git checkout      -> the source was a linked worktree, whose .gitfile
#                                  points outside the single dir mounted in the container
#   orphan or unmerged commit?  -> the clone had copied a stale refs/remotes/origin/main
#   no functional ubireader     -> ~/.local/bin wrapper existed but died at import
#   missing=bwrap,slirp4netns   -> both installed under ~/.local/bin, which was off PATH
#
# scripts/build-astro-v96.sh solved some of this but hardcodes v96's id, pin,
# summary path and output directory, so nobody reaches for it on the next version
# and each release re-derives the whole invocation by hand. That is how v95 was
# built from an ad-hoc tree with a regressed pin.
#
# WHAT THIS DOES
#   1. Runs scripts/build-doctor.sh first, so a broken host is reported in seconds
#      instead of minutes into a build.
#   2. PROVISIONS what it safely can, inside the repo, without touching $HOME:
#        - a private bin dir with a docker shim and the ubireader bridge, prepended
#          to the child's PATH only
#        - a host-visible TMPDIR under out/, because /tmp may be sandbox-private
#        - a self-contained libgphoto2 clone at the requested pin, with remote refs
#          refreshed from the canonical repo so reachability is tested against the
#          real tip rather than a stale copy
#   3. Refuses anything it cannot fix, with the exact command to run.
#   4. Verifies the ARTIFACTS after the build, not just the exit code -- a run can
#      write FwPkt.zip at [2/7] and fail at the [5/7] gate, and "it exited 0" is not
#      evidence a candidate exists.
#   5. Never deletes a completed candidate.
#
# Nothing here installs software, flashes firmware or touches a camera.
#
# Usage:
#   scripts/build-astro.sh --version N [--summary FILE] [options]
#
# Required:
#   --version N          candidate number; sets id astro-vN-<slug>-<date> and fwver 6.0.0.54.N
#                        (or pass --display-fwver to override)
#   --summary FILE       change-summary JSON. If omitted, a template is written for
#                        you to fill in -- the builder requires one and it is the
#                        release's honest statement of what changed.
#
# Options:
#   --slug NAME          short name in the candidate id (default: build)
#   --pin SHA            libgphoto2 commit (default: origin/main tip of the canonical repo)
#   --libgphoto2 DIR     existing self-contained clone to use instead of provisioning
#   --stock FILE         stock FwPkt.zip (default: the BenroPolarisPatcher copy)
#   --catalog DIR        catalogue package (default: gaia-dr3-g10)
#   --display-fwver V    override the derived 6.0.0.54.N
#   --focal MIN-MAX      focal range in mm (default 14-400)
#   --sensor MM          sensor width in mm (default 36)
#   --skip-doctor        do not run build-doctor.sh first (not recommended)
#   --dry-run            provision and print the command, but do not build
#   -h | --help

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# --- defaults -----------------------------------------------------------------
LIB_REPO="/home/ian/Documents/VSCodeProjects/LibGphoto2/libgphoto2"
STOCK_DEFAULT="/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/firmware/FwPkt.zip"
CATALOG_DEFAULT="/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher/out/gaia-dr3-g10"
CAMERA_BASELINE="397320411a1355f06d21233435e144d24efc4207"   # shared standard camera packet
PREVIOUS_PIN="43dccb81b92b6b25f44957a4684f534393562028"      # v94 pin; superset gate baseline

VERSION="" SLUG="build" SUMMARY="" PIN="" LIBSRC="" STOCK="$STOCK_DEFAULT"
CATALOG="$CATALOG_DEFAULT" FWVER="" FMIN=14 FMAX=400 SENSOR=36
SKIP_DOCTOR=0 DRY_RUN=0

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }

usage() { sed -n '1,58p' "${BASH_SOURCE[0]}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --version)     VERSION="$2"; shift 2;;
        --slug)        SLUG="$2"; shift 2;;
        --summary)     SUMMARY="$2"; shift 2;;
        --pin)         PIN="$2"; shift 2;;
        --libgphoto2)  LIBSRC="$2"; shift 2;;
        --stock)       STOCK="$2"; shift 2;;
        --catalog)     CATALOG="$2"; shift 2;;
        --display-fwver) FWVER="$2"; shift 2;;
        --focal)       FMIN="${2%%-*}"; FMAX="${2##*-}"; shift 2;;
        --sensor)      SENSOR="$2"; shift 2;;
        --skip-doctor) SKIP_DOCTOR=1; shift;;
        --dry-run)     DRY_RUN=1; shift;;
        -h|--help)     usage; exit 0;;
        *) die "unknown argument: $1 (see --help)";;
    esac
done

case "$VERSION" in ''|*[!0-9]*) die "--version must be a number (got '${VERSION:-<empty>}')";; esac
[ -f "$STOCK" ] || die "stock FwPkt not found: $STOCK"
[ -d "$CATALOG/tiles" ] || die "catalogue package has no tiles/: $CATALOG"

DATE="$(date +%Y%m%d)"
CANDIDATE_ID="astro-v${VERSION}-${SLUG}-${DATE}"
[ -n "$FWVER" ] || FWVER="6.0.0.54.${VERSION}"
OUT="$ROOT/out/$CANDIDATE_ID"

# --- 1. change summary --------------------------------------------------------
# The builder requires a summary and it is the release's honest account of what
# changed, so this never invents one. If none is given, write a template with the
# real baseline filled in and stop.
if [ -z "$SUMMARY" ]; then
    SUMMARY="$ROOT/docs/release-change-summary-v${VERSION}-astro.json"
    if [ ! -f "$SUMMARY" ]; then
        BASE_PATCHER="$(git -C "$ROOT" rev-parse HEAD)"
        cat > "$SUMMARY" <<EOF
{
  "baseline": {
    "candidate_id": "REPLACE-with-the-previous-candidate-id",
    "libgphoto2_commit": "${PIN:-REPLACE-with-the-pinned-driver-commit}",
    "libgphoto2_ref": "REPLACE: which branch carries this commit and why it is the right pin",
    "patcher_commit": "${BASE_PATCHER}",
    "patcher_ref": "the tree this was built from, and how it relates to the previous candidate",
    "previous_candidate_pins": {}
  },
  "purpose": "REPLACE: what this candidate is for, in plain language.",
  "changes": [
    {
      "component": "REPLACE-one-of: libgphoto2|patcher|packaging|tests|docs",
      "summary": "REPLACE: the change, and why it matters.",
      "issues": []
    }
  ],
  "known_limits": [
    "REPLACE: every known limitation. Deferred or unfixed work belongs here, stated plainly."
  ],
  "validation_focus": [
    "REPLACE: what to test on hardware before this is called a release."
  ]
}
EOF
        printf '\nWrote a change-summary template:\n  %s\n' "$SUMMARY"
        printf 'Fill it in, then re-run. It must state honestly what changed and\n'
        printf 'what is NOT fixed -- that file is what ships with the release.\n'
        printf '\nThen:\n  scripts/build-astro.sh --version %s --slug %s --summary %s\n' \
            "$VERSION" "$SLUG" "${SUMMARY#$ROOT/}"
        exit 0
    fi
fi
[ -f "$SUMMARY" ] || die "change summary not found: $SUMMARY"
python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$SUMMARY" \
    || die "change summary is not valid JSON: $SUMMARY"

# Two guards that exist because I made this mistake myself on 2026-11-06 while
# verifying the wrapper: I passed a v97 summary to a --version 98 build, and it
# was accepted. The resulting candidate carried a valid manifest with valid
# digests and a change summary describing a DIFFERENT release. That is worse than
# a failed build, because it looks finished.

# An unfilled template must never be built with. The template is written by this
# script and is deliberately not a valid release summary.
if grep -q 'REPLACE' "$SUMMARY"; then
    die "$SUMMARY still contains REPLACE placeholders. Fill every one in first;
       the change summary ships inside the release and states what changed and
       what is NOT fixed."
fi

# A summary named for another version is almost always the wrong file. Refuse
# rather than silently misdescribe the release; --allow-summary-version-mismatch
# is there for the legitimate case of reusing a reviewed summary deliberately.
SUMMARY_VER="$(basename "$SUMMARY" | grep -oE 'v[0-9]+' | head -1 | tr -d 'v')"
if [ -n "$SUMMARY_VER" ] && [ "$SUMMARY_VER" != "$VERSION" ] \
        && [ "${ALLOW_SUMMARY_VERSION_MISMATCH:-0}" != 1 ]; then
    die "change summary $(basename "$SUMMARY") is named for v$SUMMARY_VER but this
       build is v$VERSION. The summary is embedded in the candidate manifest, so
       this would ship a release describing a different release.
       Write docs/release-change-summary-v${VERSION}-astro.json (running without
       --summary writes a template), or pass
       ALLOW_SUMMARY_VERSION_MISMATCH=1 if reusing it is deliberate."
fi

# --- 2. never destroy a completed candidate ---------------------------------
# Checked here, before anything else can fail. build-astro-candidate.sh does
# `rm -rf` on --out when given --force, so this is the one guard that protects
# real work. If it ran after source validation, a re-run with both a bad pin and
# an existing candidate would report the pin and never warn that the next step
# deletes a finished build.
FORCE=()
if [ -e "$OUT" ]; then
    if [ -s "$OUT/astro-candidate-manifest.json" ]; then
        die "$OUT already holds a COMPLETED candidate. Refusing to delete it.
       To rebuild, use a different --slug or --version, or remove it yourself:
         rm -rf '$OUT'"
    fi
fi

# --- 3. environment the build needs ------------------------------------------
# Everything below is written under out/, so nothing here modifies $HOME or the
# system. The shims are only on the child's PATH.
ENVBIN="$ROOT/out/.build-env/bin"
TMPROOT="$ROOT/out/.build-env/tmp"
mkdir -p "$ENVBIN" "$TMPROOT" || die "could not create $ROOT/out/.build-env"

# TMPDIR: mktemp must land where the Docker daemon can see it. Inside a Flatpak,
# /tmp is private to the sandbox while the daemon runs on the host, so mounting a
# /tmp path yields an empty /in -- reported as "firmwareInfo not found".
export TMPDIR="$TMPROOT"

# docker: a plain `docker` must exist and reach a daemon.
if ! (command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1); then
    if command -v flatpak-spawn >/dev/null 2>&1 \
            && flatpak-spawn --host docker info >/dev/null 2>&1; then
        printf '#!/bin/sh\nexec flatpak-spawn --host docker "$@"\n' > "$ENVBIN/docker"
        chmod +x "$ENVBIN/docker"
        note "docker: wrote a flatpak-spawn shim at out/.build-env/bin/docker"
    else
        die "no usable docker. Inside Flatpak run:
       flatpak override --user --filesystem=/var/run/docker.sock \$FLATPAK_ID
     then fully quit and relaunch the app. Or start the daemon:
       sudo systemctl start docker"
    fi
fi

# ubireader: prefer a working native install; otherwise use the committed bridge,
# which runs the patcher image's ubireader against host paths.
if command -v ubireader_extract_files >/dev/null 2>&1 \
        && ubireader_extract_files --help >/dev/null 2>&1; then
    UBI="$(command -v ubireader_extract_files)"
    note "ubireader: using native $UBI"
else
    [ -x "$ROOT/tools/ubireader-docker" ] || die "tools/ubireader-docker missing or not executable"
    UBI="$ROOT/tools/ubireader-docker"
    note "ubireader: native install absent or broken; using the Docker bridge"
fi
export UBIREADER_EXTRACT_FILES="$UBI"

# PATH: ~/.local/bin commonly holds bwrap and slirp4netns, which the [5/7] gate
# requires to be findable. Its absence there produces "missing=bwrap", which tells
# you to install software that is already installed.
case ":$PATH:" in (*":$ENVBIN:"*) ;; (*) PATH="$ENVBIN:$PATH";; esac
[ -d "$HOME/.local/bin" ] && case ":$PATH:" in
    (*":$HOME/.local/bin:"*) ;; (*) PATH="$PATH:$HOME/.local/bin";; esac
export PATH

# --- 4. libgphoto2 source: self-contained clone at the pin -------------------
# Must be a real clone, never a worktree: only $LIBSRC is mounted into the
# container, and a worktree's .gitfile points outside it, so git inside the
# container cannot resolve it ("must be a Git checkout").
if [ -z "$LIBSRC" ]; then
    LIBSRC="$ROOT/out/.libgphoto2-v${VERSION}"
    if [ ! -d "$LIBSRC/.git" ]; then
        [ -e "$LIBSRC" ] && die "$LIBSRC exists but is not a git clone; remove it or pass --libgphoto2"
        [ -d "$LIB_REPO" ] || die "canonical libgphoto2 repo not found: $LIB_REPO"
        note "cloning libgphoto2 (shared objects) into out/.libgphoto2-v${VERSION}"
        git clone --no-checkout --local "$LIB_REPO" "$LIBSRC" >/dev/null 2>&1 \
            || die "could not clone $LIB_REPO into $LIBSRC"
    fi
    [ -d "$LIBSRC/.git" ] || die "$LIBSRC is a git worktree or not a repo; the build needs a self-contained clone"

    # Resolve the pin. Default to the canonical repo's origin/main tip, which is
    # where driver work lands.
    if [ -z "$PIN" ]; then
        PIN="$(git -C "$LIB_REPO" rev-parse origin/main 2>/dev/null)" \
            || die "could not read origin/main in $LIB_REPO; pass --pin explicitly"
        note "driver pin defaults to canonical origin/main: ${PIN:0:9}"
    fi

    # Refresh remote-tracking refs from the canonical repo. A local clone copies
    # whatever refs/remotes/origin/* the source had, which may be stale; testing
    # reachability against a stale tip makes a good pin look orphaned. That cost
    # one attempt on 2026-11-06.
    git -C "$LIBSRC" fetch -q "$LIB_REPO" '+refs/remotes/origin/*:refs/remotes/origin/*' 2>/dev/null \
        || note "warning: could not refresh origin refs in $LIBSRC"

    git -C "$LIBSRC" cat-file -e "${PIN}^{commit}" 2>/dev/null \
        || die "pin ${PIN:0:9} is not present in $LIBSRC; fetch it from the canonical repo first"
    git -C "$LIBSRC" checkout -q --detach "$PIN" 2>/dev/null \
        || die "could not check out ${PIN:0:9} in $LIBSRC (dirty tree?)"
fi

[ -d "$LIBSRC/.git" ] || die "$LIBSRC is not a self-contained git clone (a worktree will not work; see header)"
[ -f "$LIBSRC/configure.ac" ] || die "$LIBSRC has no configure.ac -- not a libgphoto2 checkout"
ACTUAL_PIN="$(git -C "$LIBSRC" rev-parse HEAD)"
if [ -n "$(git -C "$LIBSRC" status --porcelain --untracked-files=all)" ]; then
    die "$LIBSRC is dirty. The build compiles what is on disk, so a dirty tree
       produces a candidate whose recorded pin does not describe its contents."
fi
for stale in build _build build-asan; do
    [ -d "$LIBSRC/$stale" ] && die "$LIBSRC has a stale $stale/ directory; remove it (the build refuses this)"
done

# Reachability, checked here so the message is actionable before a long build.
REACH=0
for ref in origin/main origin/feature/polaris-capture-events; do
    git -C "$LIBSRC" rev-parse -q --verify "$ref^{commit}" >/dev/null 2>&1 || continue
    git -C "$LIBSRC" merge-base --is-ancestor "$ACTUAL_PIN" "$ref" 2>/dev/null && REACH=1 && break
done
if [ "$REACH" != 1 ]; then
    die "pin ${ACTUAL_PIN:0:9} is not reachable from this clone's origin/main or
       origin/feature/polaris-capture-events. Before believing it is orphaned,
       refresh the refs -- a local clone copies whatever origin/* the source had:
         git -C $LIBSRC fetch $LIB_REPO 'refs/remotes/origin/*:refs/remotes/origin/*'"
fi

# Superset gate: a new pin must carry everything the previous pin carried. This is
# the check that would have caught v95 shipping without the #251 guard.
if [ "$ACTUAL_PIN" != "$PREVIOUS_PIN" ]; then
    if git -C "$LIBSRC" cat-file -e "${PREVIOUS_PIN}^{commit}" 2>/dev/null; then
        bash "$ROOT/scripts/pin-divergence-check.sh" "$LIBSRC" "$ACTUAL_PIN" "$PREVIOUS_PIN" \
            || die "pin ${ACTUAL_PIN:0:9} is not a superset of the v94 pin -- refusing to build a regressed candidate"
    else
        die "cannot verify superset: previous pin ${PREVIOUS_PIN:0:9} absent from $LIBSRC"
    fi
fi

# --- 5. patcher tree must be committed ---------------------------------------
[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ] && \
    die "patcher tree is dirty; commit first. Provenance records the exact commit,
       so a dirty tree makes that record a lie about what was compiled."

# --- 7. clear incomplete output from a previous failed run -------------------
# Safe now: the completed-candidate check above already refused that case, so
# anything present here is a partial from a run that never wrote its manifest.
if [ -e "$OUT" ]; then
    note "clearing incomplete output from a previous failed run at ${OUT#$ROOT/}"
    find "$OUT" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
    FORCE=(--force)
fi

# --- 8. doctor ---------------------------------------------------------------
if [ "$SKIP_DOCTOR" != 1 ]; then
    echo "=== preflight: scripts/build-doctor.sh ==="
    if ! bash "$ROOT/scripts/build-doctor.sh" --libgphoto2 "$LIBSRC" --stock "$STOCK" --catalog "$CATALOG"; then
        die "preflight is RED. Fix the FAIL lines above (each prints the exact
       command) or re-run with --skip-doctor if you have read them and disagree."
    fi
    echo
fi

# --- 9. build ----------------------------------------------------------------
echo "============================================================"
echo "candidate      $CANDIDATE_ID"
echo "display fwver  $FWVER"
echo "driver pin     ${ACTUAL_PIN:0:9}"
echo "patcher commit $(git -C "$ROOT" rev-parse --short HEAD)"
echo "summary        ${SUMMARY#$ROOT/}"
echo "output         ${OUT#$ROOT/}"
echo "============================================================"

if [ "$DRY_RUN" = 1 ]; then
    echo
    echo "dry run: would execute"
    printf '  scripts/build-astro-candidate.sh \\\n'
    printf '    --id %s --stock-fwpkt %s \\\n' "$CANDIDATE_ID" "${STOCK#$HOME/}"
    printf '    --libgphoto2-source %s --libgphoto2-commit %s \\\n' "${LIBSRC#$ROOT/}" "$ACTUAL_PIN"
    printf '    --display-fwver %s --build-id %s \\\n' "$FWVER" "$CANDIDATE_ID"
    printf '    --camera-baseline %s --catalog-package %s \\\n' "$CAMERA_BASELINE" "${CATALOG#$HOME/}"
    printf '    --change-summary %s --focal-min %s --focal-max %s --sensor-mm %s\n' \
        "${SUMMARY#$ROOT/}" "$FMIN" "$FMAX" "$SENSOR"
    exit 0
fi

LOG="$ROOT/out/logs/$CANDIDATE_ID.log"
mkdir -p "$(dirname "$LOG")"

# Not exec: the exit code alone cannot say whether a candidate exists. A build can
# fail after writing partial output, and then "it exited quickly" is indistinguishable
# from success. Verify the artifacts themselves.
rc=0
bash "$ROOT/scripts/build-astro-candidate.sh" \
  --id "$CANDIDATE_ID" \
  --stock-fwpkt "$STOCK" \
  --libgphoto2-source "$LIBSRC" \
  --display-fwver "$FWVER" \
  --build-id "$CANDIDATE_ID" \
  --camera-baseline "$CAMERA_BASELINE" \
  --libgphoto2-commit "$ACTUAL_PIN" \
  --catalog-package "$CATALOG" \
  --change-summary "$SUMMARY" \
  --focal-min "$FMIN" --focal-max "$FMAX" --sensor-mm "$SENSOR" \
  --out "$OUT" ${FORCE[@]+"${FORCE[@]}"} 2>&1 | tee "$LOG"
rc="${PIPESTATUS[0]}"

echo "============================================================"
if [ "$rc" -eq 0 ] && [ -s "$OUT/FwPkt.zip" ] && [ -s "$OUT/astro-candidate-manifest.json" ]; then
    echo "BUILD SUCCEEDED: $CANDIDATE_ID ($FWVER)"
    note "FwPkt.zip  sha256 $(sha256sum "$OUT/FwPkt.zip" | cut -c1-32)..."
    note "bundle     sha256 $(sha256sum "$OUT/astro-bundle.tar.gz" | cut -c1-32)..."
    note "log        ${LOG#$ROOT/}"
    echo
    echo "NOT INSTALLED. Nothing was staged, flashed or uploaded."
    echo "Physical qualification on a real camera is still required."
    echo "Register the hashes in docs/FWPKT-PROVENANCE-CONTRACT.md before publishing."
else
    echo "BUILD FAILED (exit $rc)"
    [ -s "$OUT/FwPkt.zip" ] && echo "  WARNING: a partial FwPkt.zip exists -- do NOT use it"
    note "log ${LOG#$ROOT/}"
    if [ -f "$LOG" ]; then
        echo "  last lines:"
        tail -20 "$LOG" | sed 's/^/    /'
    fi
fi
echo "============================================================"
exit "$rc"
