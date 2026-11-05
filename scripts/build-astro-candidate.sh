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
LIB_BASELINE="3fb26e536ac169e4970d69516a9d45daf62563f5"
# The pin the previous shipped Astro candidate used. A new pin must be a superset of it, not merely
# reachable from a branch: 855f718e is reachable from feature/polaris-capture-events yet is missing
# nine shipped-code commits that driver main gained after the branches diverged at 83240b36a on
# 2026-10-28 (stale-session safety barriers, deferred Bulb cancellation, IT2 white-balance alias,
# RAW container format, AF release mode, K-1 live-view contract). Pinning it would regress v94.
PREVIOUS_LIB_BASELINE="43dccb81b92b6b25f44957a4684f534393562028"
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
[ "$LIB_REACHABLE" = 1 ] || die "libgphoto2 baseline $LIB_BASELINE is not reachable from origin/main or origin/feature/polaris-capture-events -- orphan or unmerged commit?"
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
