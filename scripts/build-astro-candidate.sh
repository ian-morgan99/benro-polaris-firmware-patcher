#!/usr/bin/env bash
# Build a separately identified Astro candidate without deploying it.
# The FwPkt uses the same patch-polaris.sh camera path as standard firmware.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ID="" STOCK="" LIBSRC="" OUT="" DISPLAY_FWVER="" BUILD_ID=""
CAMERA_BASELINE="8c015c0a73c8affea8fa723badcceb4070ef81b4"
LIB_BASELINE="051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff"
CATALOG_PACKAGE="" FMIN="14" FMAX="400" SENSOR="36"
ASTRO_SRC_CACHE="${ASTRO_SRC_CACHE:-$ROOT/out/.astro-src-cache}"
FORCE=0 NO_INDEXES=0 IMAGE="${POLARIS_PATCHER_IMAGE:-polaris-patcher}"

usage() {
  cat >&2 <<'EOF'
usage: scripts/build-astro-candidate.sh --id ID --stock-fwpkt PATH \
  --libgphoto2-source PATH --display-fwver X.Y.Z.N.M --build-id ID \
  --catalog-package DIR [options]

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
[ -n "$DISPLAY_FWVER" ] && [ -n "$BUILD_ID" ] && [ -n "$CATALOG_PACKAGE" ] || usage
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
[ "$(git -C "$LIBSRC" branch --show-current)" = "main" ] || die "libgphoto2 must be on main"
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

echo "[6/7] recording source and feature binding"
{
  echo "candidate_variant=astro"
  echo "candidate_id=$ID"
  echo "display_fwver=$DISPLAY_FWVER"
  echo "build_id=$BUILD_ID"
  echo "patcher_commit=$(git -C "$ROOT" rev-parse HEAD)"
  echo "shared_camera_baseline=$CAMERA_BASELINE"
  echo "astro_commit=$(git -C "$ROOT" rev-parse HEAD)"
  echo "libgphoto2_commit=$LIB_BASELINE"
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
cat > "$OUT/install-status.txt" <<EOF
candidate_variant=astro
candidate_id=$ID
install_status=not-installed
deployment=not-performed
EOF

echo "[7/7] candidate complete (build-only)"
echo "candidate=$OUT"
echo "manifest=$OUT/astro-candidate-manifest.json"
echo "FwPkt=$OUT/FwPkt.zip"
echo "AstroBundle=$OUT/astro-bundle.tar.gz"
echo "No deployment, reboot, flash, or upload was performed."
