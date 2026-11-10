#!/usr/bin/env bash
# Build a separately identified Astro candidate without deploying it.
# The FwPkt uses the same patch-polaris.sh camera path as standard firmware.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ID="" STOCK="" LIBSRC="" OUT="" DISPLAY_FWVER="" BUILD_ID=""
CHANGE_SUMMARY=""
CAMERA_BASELINE="397320411a1355f06d21233435e144d24efc4207"
# Driver pin: libgphoto2 main. Moved off feature/polaris-capture-events on
# 2026-11-05, when that branch was fast-forwarded into main as 3fb26e536.
# Carries #233 capability row + #235 K-1 II shutter gate (both from PR #144,
# previously verified by content: pentax_model_answers_undeclared_generic_props
# and pentax_shutter_write_permitted), plus the deferred-Bulb cancellation fix
# from PR #139 and 17 commits that were on the feature branch but never on main.
# Verified a clean superset of the previous pin by scripts/pin-divergence-check.sh.
# Advanced to 7e6dec95f on 2026-11-08 for the v99 candidate. Driver main had moved past
# v97's pin while work accumulated unreleased on feature/astro-native-platesolve, so the
# tree was building from a driver commit that no release had ever named. The delta is one
# commit and it is documentation only ("docs: state which repo owns which work"), verified:
#   git log --oneline 3fb26e536..7e6dec95f  -> exactly one line, no camlib or library source
#   scripts/pin-divergence-check.sh         -> ancestry OK, patch-equiv 0 missing, PASS
# So the shipped .so set is unchanged from v97 and can be checked byte-for-byte against
# v97's install-manifest.json. Advancing here costs nothing and stops the pin drifting.
LIB_BASELINE="7e6dec95f383ba5902ed2a7ee6c11cd48a359188"
# The pin the previous shipped Astro candidate used. A new pin must be a superset of it, not merely
# reachable from a branch: 855f718e is reachable from feature/polaris-capture-events yet is missing
# nine shipped-code commits that driver main gained after the branches diverged at 83240b36a on
# 2026-10-28 (stale-session safety barriers, deferred Bulb cancellation, IT2 white-balance alias,
# RAW container format, AF release mode, K-1 live-view contract). Pinning it would regress v94.
# Set to v97's pin rather than v94's: v97 is the last candidate that was actually published and
# run on hardware, so that is the release this one must be proved not to regress. The gate runs
# only when LIB_BASELINE differs from this value, so leaving it at v94 would have skipped the
# comparison against the release that matters.
PREVIOUS_LIB_BASELINE="3fb26e536ac169e4970d69516a9d45daf62563f5"
CATALOG_PACKAGE="" FMIN="14" FMAX="400" SENSOR="36"
ASTRO_SRC_CACHE="${ASTRO_SRC_CACHE:-$ROOT/out/.astro-src-cache}"
FORCE=0 NO_INDEXES=0 IMAGE="${POLARIS_PATCHER_IMAGE:-polaris-patcher}"

usage() {
  cat >&2 <<'EOF'
usage: scripts/build-astro-candidate.sh --id ID --stock-fwpkt PATH \
  --libgphoto2-source PATH --display-fwver X.Y.Z.N.M --build-id ID \
  --catalog-package DIR --change-summary FILE [options]

Build-only Astro candidate. Output contains FwPkt/ and additive
astro-bundle/. This never stages, reboots, flashes, or uploads.
options: --camera-baseline SHA --libgphoto2-commit SHA
  --focal-min MM --focal-max MM --sensor-mm MM
  --astro-src-cache DIR --image NAME --no-indexes --out DIR --force
EOF
  exit 2
}
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --id) ID="$2"; shift 2;; --stock-fwpkt) STOCK="$2"; shift 2;;
    --libgphoto2-source) LIBSRC="$2"; shift 2;;
    --display-fwver) DISPLAY_FWVER="$2"; shift 2;; --build-id) BUILD_ID="$2"; shift 2;;
    --change-summary) CHANGE_SUMMARY="$2"; shift 2;;
    --camera-baseline) CAMERA_BASELINE="$2"; shift 2;;
    --libgphoto2-commit) LIB_BASELINE="$2"; shift 2;;
    --catalog-package) CATALOG_PACKAGE="$2"; shift 2;;
    --focal-min) FMIN="$2"; shift 2;; --focal-max) FMAX="$2"; shift 2;;
    --sensor-mm) SENSOR="$2"; shift 2;; --astro-src-cache) ASTRO_SRC_CACHE="$2"; shift 2;;
    --image) IMAGE="$2"; shift 2;; --no-indexes) NO_INDEXES=1; shift;;
    --out) OUT="$2"; shift 2;; --force) FORCE=1; shift;; -h|--help) usage;;
    *) die "unknown option: $1";;
  esac
done
[ -n "$ID" ] && [ -n "$STOCK" ] && [ -n "$LIBSRC" ] &&
[ -n "$DISPLAY_FWVER" ] && [ -n "$BUILD_ID" ] && [ -n "$CATALOG_PACKAGE" ] &&
[ -n "$CHANGE_SUMMARY" ] || usage
[ -f "$CHANGE_SUMMARY" ] || die "change summary does not exist: $CHANGE_SUMMARY"
# Parse it NOW. The file is only read at step 6/7 by create-astro-candidate-manifest.py,
# so a trailing comma or an unescaped quote is reported after a full multi-minute firmware
# build has already been spent -- and the build output is left half-written. I hit exactly
# that writing the v99 summary. Fail in milliseconds with the parser's line and column.
python3 -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" \
  "$CHANGE_SUMMARY" 2>/dev/null || die "change summary is not valid JSON: $CHANGE_SUMMARY
       $(python3 -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" \
          "$CHANGE_SUMMARY" 2>&1 | tail -1)"
case "$ID" in (*[!a-zA-Z0-9._-]*) die "invalid candidate id: $ID";; esac
case "$DISPLAY_FWVER" in (*[!0-9.]*|.*|*..*|*.) die "invalid display version";; esac
case "$DISPLAY_FWVER" in (*.*.*.*.*) ;; (*) die "need five-component display version";; esac
case "$CAMERA_BASELINE$LIB_BASELINE" in (*[!0-9a-f]*) die "baseline commits must be lower-case SHAs";; esac
[ "$(printf %s "$CAMERA_BASELINE" | wc -c)" -eq 40 ] || die "camera baseline must be full SHA"
[ "$(printf %s "$LIB_BASELINE" | wc -c)" -eq 40 ] || die "libgphoto2 baseline must be full SHA"

BRANCH="$(git -C "$ROOT" branch --show-current)"
[ "$BRANCH" = "feature/astro-native-platesolve" ] || die "wrong Astro branch: $BRANCH"
TREE_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"
[ -z "$TREE_STATUS" ] || die "Astro source tree is dirty; use a clean clone"
git -C "$ROOT" diff --check || die "Astro source whitespace errors"
git -C "$ROOT" cat-file -e "$CAMERA_BASELINE^{commit}" || die "camera baseline is not present"
git -C "$ROOT" merge-base --is-ancestor "$CAMERA_BASELINE" HEAD || die "camera baseline is not in Astro HEAD"

[ -d "$LIBSRC" ] || die "libgphoto2 source must be a checkout"
# The pinned commit must be reachable from a real branch on origin, so provenance always
# points at something a third party can fetch. A detached checkout at that SHA is fine; an
# orphan is not. Driver main carries the v94 pin (43dccb81b). feature/polaris-capture-events
# carries #233 (pentax_model_answers_undeclared_generic_props) and, once PR #144 is merged,
# the #235 shutter gate -- so a v95 pin lives there, not on main.
LIB_REACHABLE=0
for LIB_REF in origin/main origin/feature/polaris-capture-events; do
  git -C "$LIBSRC" rev-parse -q --verify "$LIB_REF^{commit}" >/dev/null || continue
  if git -C "$LIBSRC" merge-base --is-ancestor "$LIB_BASELINE" "$LIB_REF" 2>/dev/null; then
    LIB_REACHABLE=1
    break
  fi
done
[ "$LIB_REACHABLE" = 1 ] || {
  # "orphan or unmerged commit?" was misleading on 2026-11-06: the pin WAS on
  # origin/main, but this clone had been created from a local repo whose
  # refs/remotes/origin/main was stale, so the ancestor test ran against the wrong
  # tip and a perfectly good commit looked orphaned. Distinguish the two cases here
  # rather than making the operator guess and go chase the wrong thing.
  echo "ERROR: libgphoto2 baseline $LIB_BASELINE is not reachable from origin/main"
  echo "       or origin/feature/polaris-capture-events in $LIBSRC."
  if git -C "$LIBSRC" cat-file -e "${LIB_BASELINE}^{commit}" 2>/dev/null; then
    echo "       The commit IS present locally, so this is one of two things:"
    echo "         (a) a stale remote-tracking ref -- very common when the clone was"
    echo "             made from another local repo rather than fetched from GitHub."
    echo "             Check what this clone thinks main is:" $(git -C "$LIBSRC" rev-parse --short origin/main 2>/dev/null || echo '(absent)')
    echo "             Refresh it and retry:"
    echo "               git -C $LIBSRC fetch origin 'refs/remotes/origin/*:refs/remotes/origin/*'"
    echo "         (b) genuinely unmerged -- the commit exists only on a local branch."
    echo "             Verify against the real remote before believing this."
  else
    echo "       The commit is not even present in $LIBSRC. Fetch it:"
    echo "         git -C $LIBSRC fetch origin $LIB_BASELINE"
  fi
  exit 1
}
# Reachability proves nothing about *completeness*. When the pin changes, require that it still
# carries everything the previous pin carried. Fail closed: if the previous pin cannot be inspected
# in this checkout, that is itself a reason not to build.
if [ "$LIB_BASELINE" != "$PREVIOUS_LIB_BASELINE" ]; then
  if ! git -C "$LIBSRC" cat-file -e "${PREVIOUS_LIB_BASELINE}^{commit}" 2>/dev/null; then
    die "cannot verify superset: previous pin $PREVIOUS_LIB_BASELINE is not present in $LIBSRC (fetch it)"
  fi
  bash "$ROOT/scripts/pin-divergence-check.sh" "$LIBSRC" "$LIB_BASELINE" "$PREVIOUS_LIB_BASELINE" \
    || die "libgphoto2 pin is not a superset of the previous pin; refusing to build a regressed candidate"
fi
[ "$(git -C "$LIBSRC" rev-parse HEAD)" = "$LIB_BASELINE" ] || die "wrong libgphoto2 commit"
[ -z "$(git -C "$LIBSRC" status --porcelain --untracked-files=all)" ] || die "libgphoto2 source is dirty"
for stale in build _build build-asan; do [ ! -d "$LIBSRC/$stale" ] || die "libgphoto2 has stale $stale/"; done
[ -e "$STOCK" ] || die "stock FwPkt does not exist: $STOCK"
[ -d "$CATALOG_PACKAGE/tiles" ] || die "catalogue package has no tiles/"
for required in tiles.json tiles.ptri tiles.ptri.json; do
  [ -f "$CATALOG_PACKAGE/$required" ] || die "catalogue package missing $required"
done

if [ -z "$OUT" ]; then OUT="$ROOT/out/$ID"; elif [[ "$OUT" != /* ]]; then OUT="$ROOT/$OUT"; fi
OUT="$(realpath -m "$OUT")"; ROOT_REAL="$(realpath -m "$ROOT")"
case "$OUT" in "$ROOT_REAL/out/"*) ;; (*) die "output must be below out/";; esac
[ "$OUT" != "$ROOT_REAL/out" ] || die "refusing whole out/"
[ ! -L "$OUT" ] || die "refusing symlink output"
if [ -e "$OUT" ]; then [ "$FORCE" = 1 ] || die "output exists; use --force"; rm -rf -- "$OUT"; fi
mkdir -p "$OUT"

# ---------------------------------------------------------------------------
# Prerequisites, checked BEFORE the first build step (#306 follow-up).
#
# The doctor used to run only inside scripts/build-astro.sh, which this script
# calls at step [2/7]. Step [1/7] is patch-polaris.sh -- the long camera build --
# so on 2026-11-09 a broken host was discovered *after* the expensive part had
# already been attempted, and the failure surfaced as "no usable docker" from a
# script that had nothing to do with the cause. Checking here moves that to seconds.
#
# Provision first so the doctor sees the environment the build will actually use,
# otherwise it reports blockers this wrapper would have handled anyway: TMPDIR must
# be host-visible (patch-polaris.sh extracts the stock packet with mktemp -d and
# bind-mounts it, and /tmp is private to the sandbox), and a broken native ubireader
# has a working bridge in-repo.
ENVBIN="$ROOT/out/.build-env/bin"
TMPROOT="$ROOT/out/.build-env/tmp"
mkdir -p "$ENVBIN" "$TMPROOT" || die "could not create $ROOT/out/.build-env"
export TMPDIR="$TMPROOT"
case ":$PATH:" in (*":$ENVBIN:"*) ;; (*) PATH="$ENVBIN:$PATH";; esac
export PATH
if ! (command -v ubireader_extract_files >/dev/null 2>&1 \
      && ubireader_extract_files --help >/dev/null 2>&1); then
  [ -x "$ROOT/tools/ubireader-docker" ] || die "tools/ubireader-docker missing"
  export UBIREADER_EXTRACT_FILES="$ROOT/tools/ubireader-docker"
fi

# Put a working `docker` on the child's PATH. This is the systemic fix rather than
# another per-script patch: every script this wrapper invokes calls plain `docker`,
# and each one that checks independently has failed with its own wording --
# patch-polaris.sh says "Install Docker Desktop", build-astro.sh says "docker not
# found", and the host shim returns rc=127 reading like "not installed" (#308).
# Patching them one at a time is how five sites became six. $ENVBIN is already first
# on PATH and inherited by every child, so one entry here covers all of them,
# including scripts that have not been audited.
#
# The generated shim execs an ABSOLUTE host path. It must never be
# `exec flatpak-spawn --host docker "$@"`: that asks the host to resolve `docker` on
# the host's PATH, where ~/.local/bin and ~/bin sit by default, so a shim of that
# same shape on the host re-enters itself and dies.
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  . "$ROOT/tools/host-docker.sh"
  DOCKER_PREFIX="$(polaris_docker_prefix 2>/dev/null || true)"
  if [ -z "$DOCKER_PREFIX" ]; then
    echo "ERROR: no usable docker for this build." >&2
    if polaris_docker_shadowed; then
      echo "       a 'docker' IS on PATH but cannot reach a daemon." >&2
      echo "       the host resolves it to: $(polaris_host_docker_resolved)" >&2
    fi
    echo "       run scripts/build-doctor.sh, which names the exact cause." >&2
    exit 1
  fi
  printf '#!/bin/sh\n# generated by scripts/build-astro-candidate.sh -- do not edit\nexec %s "$@"\n' \
    "$DOCKER_PREFIX" > "$ENVBIN/docker"
  chmod +x "$ENVBIN/docker"
fi

echo "=== preflight: scripts/build-doctor.sh ==="
if [ "${SKIP_DOCTOR:-0}" = 1 ]; then
  echo "WARNING: --skip-doctor: build prerequisites were NOT verified." >&2
  DOCTOR_STATUS="skipped-by-flag"
elif bash "$ROOT/scripts/build-doctor.sh" --libgphoto2 "$LIBSRC" --stock "$STOCK" \
        --catalog "$CATALOG_PACKAGE" --image "$IMAGE" > "$OUT/doctor.log" 2>&1; then
  DOCTOR_STATUS="green"
  echo "build-doctor: GREEN (log: $OUT/doctor.log)"
else
  DOCTOR_STATUS="red"
  echo "ERROR: build-doctor.sh reported RED -- refusing to start a build that will" >&2
  echo "       fail later and report itself as an unrelated problem." >&2
  echo "       Full output: $OUT/doctor.log" >&2
  grep -E '^  (FAIL|WARN)' "$OUT/doctor.log" | sed 's/^/       /' >&2 || true
  echo "       Fix each FAIL line, or set SKIP_DOCTOR=1 for a documented exception." >&2
  exit 1
fi

echo "[1/7] building shared camera firmware packet"
bash "$ROOT/patch-polaris.sh" --fwpkt "$STOCK" --libgphoto2-source "$LIBSRC" \
  --enable-usb-scsi --out "$OUT" --build-id "$BUILD_ID" \
  --display-fwver "$DISPLAY_FWVER" --image "$IMAGE"

echo "[2/7] building additive native-C Astro bundle"
ASTRO_ARGS=(--out "$OUT/astro-bundle" --image "$IMAGE" --focal-min "$FMIN" \
  --focal-max "$FMAX" --sensor-mm "$SENSOR" --catalog-package "$CATALOG_PACKAGE" \
  --src-cache "$ASTRO_SRC_CACHE")
[ "$NO_INDEXES" = 1 ] && ASTRO_ARGS+=(--no-indexes)
bash "$ROOT/build-astro.sh" "${ASTRO_ARGS[@]}"
[ -d "$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT/polaris-astro" ] || die "Astro tree missing"
(
  cd "$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT"
  find . -type f -print0 | sort -z |
    while IFS= read -r -d '' file; do sha256sum "$file"; done
) > "$OUT/astro-bundle/ASTRO-MANIFEST.sha256"
[ -f "$OUT/astro-bundle/ASTRO-MANIFEST.sha256" ] || die "Astro manifest missing"

# Build the SD-rooted kit archives here, and verify them as archives.
#
# Until now this path produced no polaris-astro.zip or polaris-wifi.zip at all:
# only scripts/build-astro-bundle.sh creates them, and nothing in production calls
# that script. The zips published for 6.0.0.54.99 were therefore made outside any
# tracked build path, so the wrapper's licence gate never ran on the bytes anyone
# was handed -- polaris-wifi.zip shipped four statically-linked LGPL binaries with
# no licence and no source offer (issue #286). publish-astro-candidate.sh skips a
# missing zip silently ([ -f ] || continue), so absence passed unnoticed.
#
# Assert against the finished archive, not the staging directory: the zip is what a
# user receives, and a file that exists on disk but is excluded from the archive is
# exactly how .99 slipped through.
SD_ROOT="$OUT/astro-bundle/COPY-TO-SD-CARD-ROOT"
# Fail loudly rather than skip. Every assertion below is guarded by [ -d ]/[ -f ]
# tests, so a wrong SD_ROOT would silently skip all of them and exit 0 -- a vacuous
# pass, which is exactly the bug class in issue #286. The polaris-astro check above
# guarantees this directory exists on the real path, so reaching the die means the
# tree really is missing.
[ -d "$SD_ROOT" ] || die "SD staging tree missing: $SD_ROOT -- cannot verify the kit archives"
if [ -d "$SD_ROOT/polaris-wifi" ]; then
  command -v zip >/dev/null 2>&1 || die "wifi kit present but 'zip' is not installed -- cannot produce the archive users are given"
  (
    cd "$SD_ROOT"
    rm -f polaris-astro.zip polaris-wifi.zip
    zip -qrX polaris-astro.zip polaris-astro
    zip -qrX polaris-wifi.zip polaris-wifi
    [ -d astrometry ] && { rm -f astrometry-indexes.zip; zip -qrX astrometry-indexes.zip astrometry; }
    true
  )
fi

# The copyleft offer must be inside the archive, not merely on disk beside it.
if [ -f "$SD_ROOT/polaris-wifi.zip" ]; then
  for f in LICENCE-wifi.txt COPYING-LGPL-2.1.txt NOTICE-iw.txt NOTICE-wpa_supplicant.txt; do
    unzip -Z1 "$SD_ROOT/polaris-wifi.zip" | grep -qx "polaris-wifi/$f" \
      || die "polaris-wifi.zip does not contain $f -- shipping copyleft binaries with no licence alongside them is an LGPL s4 violation"
  done
  # Present is not enough: a zero-byte LICENCE-wifi.txt satisfies the listing above
  # and still leaves the user with nothing to read. Read the bytes out of the archive.
  for f in LICENCE-wifi.txt COPYING-LGPL-2.1.txt NOTICE-iw.txt NOTICE-wpa_supplicant.txt; do
    sz=$(unzip -p "$SD_ROOT/polaris-wifi.zip" "polaris-wifi/$f" 2>/dev/null | wc -c)
    [ "$sz" -gt 0 ] || die "polaris-wifi.zip stores $f as an empty file -- an empty licence is not a licence"
  done
  # The offer must name the versions it offers source for.
  unzip -p "$SD_ROOT/polaris-wifi.zip" polaris-wifi/LICENCE-wifi.txt \
    | grep -qE 'libnl-[0-9]+\.[0-9]' \
    || die "LICENCE-wifi.txt inside the zip names no libnl version -- an offer that names no version is not an offer"
  # Modes come from the archive, because boot gates auto-join on [ -x ]. Use plain
  # `unzip -Z`: with -Z1 the long-listing header is suppressed and this would read
  # empty, making the check pass vacuously.
  for b in wpa_supplicant wpa_cli wpa_passphrase iw polaris-autojoin.sh setup-wifi.sh udhcpc.script; do
    perm=$(unzip -Z "$SD_ROOT/polaris-wifi.zip" 2>/dev/null \
           | awk -v n="polaris-wifi/$b" '$NF==n {print $1}')
    [ -n "$perm" ] || die "polaris-wifi.zip does not contain $b at all"
    case "$perm" in
      *x*) ;;
      *) die "polaris-wifi.zip stores $b as '$perm' (not executable) -- boot's [ -x ] gate would skip it" ;;
    esac
  done
fi

# Prove the rooting claim rather than trusting the zip invocation: an entry that does
# not begin with its directory name unzips one level too deep, and the boot hook then
# installs nothing while still reporting success (issue #58).
#
# The expected root is stated per archive instead of derived from the filename, because
# astrometry-indexes.zip is intentionally rooted at astrometry/ -- the README tells users
# the card must end up with <SD root>/astrometry/index-41xx.fits. Deriving the root from
# the basename made this die on a correctly built indexes archive (11 entries), which is
# how this was caught: the assertion fired on real bytes rather than on my assumption.
for spec in "polaris-astro.zip:polaris-astro" "polaris-wifi.zip:polaris-wifi" "astrometry-indexes.zip:astrometry"; do
  zname="${spec%%:*}"; root="${spec##*:}"
  z="$SD_ROOT/$zname"
  [ -f "$z" ] || continue
  bad=$(unzip -Z1 "$z" | grep -vc "^$root/" || true)
  [ "$bad" = "0" ] || die "$z has $bad entr(ies) outside $root/ -- would not unzip to SD root"
done

tar -C "$OUT/astro-bundle" -czf "$OUT/astro-bundle.tar.gz" .

echo "[3/7] generating immutable FwPkt install manifest"
python3 "$ROOT/scripts/generate-fwpkt-manifest.py" "$OUT" \
  --ubireader "${UBIREADER_EXTRACT_FILES:-/home/ian/.local/bin/ubireader_extract_files}"

echo "[4/7] running focused Astro tests"
python3 -m pytest -q "$ROOT/container/astro/tests" "$ROOT/tools/tests" \
  "$ROOT/tests/test_astro_build_wrapper.py" "$ROOT/tests/test_plate_solving_present.py" \
  > "$OUT/astro-test-transcript.txt" 2>&1
cat "$OUT/astro-test-transcript.txt"
for script in "$ROOT"/container/astro/ondisk/*.sh; do sh -n "$script"; done

echo "[5/7] running shared camera gate against this Astro packet"
set +e
bash "$ROOT/tests/run_prerelease_gate.sh" --build "$OUT/FwPkt" \
  --libgphoto2-src "$LIBSRC" > "$OUT/shared-camera-gate.txt" 2>&1
GATE_RC="$?"
set -e
cat "$OUT/shared-camera-gate.txt"
[ "$GATE_RC" -eq 0 ] || die "shared gate RED; candidate is not publishable"

echo "[6/9] recording source and feature binding"
{
  echo "candidate_variant=astro"
  echo "candidate_id=$ID"
  echo "shared_camera_baseline=$CAMERA_BASELINE"
  echo "astro_commit=$(git -C "$ROOT" rev-parse HEAD)"
  echo "stock_input=$STOCK"
  echo "catalogue_package=$CATALOG_PACKAGE"
  echo "focal_min_mm=$FMIN"
  echo "focal_max_mm=$FMAX"
  echo "sensor_width_mm=$SENSOR"
  echo "deployment=not-performed"
  echo "firmware_flash=not-performed"
  echo "hardware_qualification=not-performed"
} >> "$OUT/build-source-provenance.txt"
python3 "$ROOT/scripts/create-astro-candidate-manifest.py" --candidate-dir "$OUT" \
  --patcher "$ROOT" --camera-baseline "$CAMERA_BASELINE" \
  --astro-commit "$(git -C "$ROOT" rev-parse HEAD)" --libgphoto2 "$LIBSRC" \
  --stock "$STOCK" --display-fwver "$DISPLAY_FWVER" --build-id "$BUILD_ID" \
  --catalogue-package "$CATALOG_PACKAGE" --focal-min "$FMIN" \
  --focal-max "$FMAX" --sensor-mm "$SENSOR"

echo "[7/9] generating immutable release identity"
python3 "$ROOT/scripts/create-release-change-manifest.py" \
  --summary "$CHANGE_SUMMARY" --candidate-id "$ID" \
  --display-fwver "$DISPLAY_FWVER" --build-id "$BUILD_ID" \
  --libgphoto2 "$LIBSRC" --patcher "$ROOT" --stock "$STOCK" \
  --candidate-dir "$OUT"
CHANGE_MANIFEST_SHA256="$(sha256sum "$OUT/release-change-manifest.json" | awk '{print $1}')"
{
  echo "release_change_manifest=release-change-manifest.json"
  echo "release_change_manifest_sha256=$CHANGE_MANIFEST_SHA256"
} >> "$OUT/build-source-provenance.txt"

echo "[8/9] checking candidate identity"
python3 "$ROOT/scripts/verify-candidate-identity.py" "$OUT" --require-deployable

echo "[9/9] recording initial install status"
cat > "$OUT/install-status.txt" <<EOF
candidate_variant=astro
candidate_id=$ID
install_status=not-installed
deployment=not-performed
EOF

echo "candidate complete (build-only)"
echo "candidate=$OUT"
echo "manifest=$OUT/astro-candidate-manifest.json"
echo "FwPkt=$OUT/FwPkt.zip"
echo "AstroBundle=$OUT/astro-bundle.tar.gz"
echo "No deployment, reboot, flash, or upload was performed."
