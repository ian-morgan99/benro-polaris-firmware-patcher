#!/usr/bin/env bash
# Build and fingerprint the additive Astro bundle for the active feature branch.
#
# This is deliberately separate from build-release-candidate.sh: it never reads,
# patches, packages, or flashes FwPkt.  The only output is an Astro bundle that
# can be copied to the Polaris SD card after its contents have been reviewed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_ID="astro-native-platesolve-$(date -u +%Y%m%dT%H%M%SZ)"
ID="${ASTRO_BUILD_ID:-$DEFAULT_ID}"
OUT=""
IMAGE="${POLARIS_PATCHER_IMAGE:-polaris-patcher-pentax}"
CATALOG_PACKAGE=""
SRC_CACHE="${ASTRO_SRC_CACHE:-$ROOT/out/.astro-src-cache}"
WANT_INDEXES=1
FORCE=0
ALLOW_MAIN=0
ALLOW_DIRTY=0
RUN_TESTS=1

ORIGINAL_ARGS=("$@")

usage() {
  cat >&2 <<'EOF'
usage: scripts/build-astro-bundle.sh [options]

Build the additive native-C Astro bundle. This does not build or modify FwPkt.

options:
  --id ID                    output id (default: timestamped astro id)
  --out DIR                  output directory under out/
  --image NAME               Docker image (default: polaris-patcher-pentax)
  --catalog-package DIR      native Gaia tile package to include
  --no-indexes               do not fetch astrometry.net FITS indexes
  --src-cache DIR            persistent upstream-source cache
  --force                    remove the selected existing output directory first
  --allow-main               permit a development build from main
  --allow-dirty              permit uncommitted source (recorded in provenance)
  --no-tests                 skip the focused Astro test and syntax gates
  -h, --help                 show this help

The normal controlled path requires the clean feature/astro-native-platesolve
branch and writes only to out/<id> plus the ignored source cache.
EOF
  exit 2
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --id)
      [ $# -ge 2 ] || usage
      ID="$2"
      shift 2
      ;;
    --out)
      [ $# -ge 2 ] || usage
      OUT="$2"
      shift 2
      ;;
    --image)
      [ $# -ge 2 ] || usage
      IMAGE="$2"
      shift 2
      ;;
    --catalog-package)
      [ $# -ge 2 ] || usage
      CATALOG_PACKAGE="$2"
      shift 2
      ;;
    --no-indexes)
      WANT_INDEXES=0
      shift
      ;;
    --src-cache)
      [ $# -ge 2 ] || usage
      SRC_CACHE="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --allow-main)
      ALLOW_MAIN=1
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --no-tests)
      RUN_TESTS=0
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage
      ;;
  esac
done

case "$ID" in
  (*[!a-zA-Z0-9._-]*) die "invalid build id: $ID" ;;
esac

command -v realpath >/dev/null 2>&1 || die "realpath is required"
ROOT_REAL="$(realpath -m "$ROOT")"
if [ -z "$OUT" ]; then
  OUT="$ROOT/out/$ID"
elif [[ "$OUT" != /* ]]; then
  OUT="$ROOT/$OUT"
fi
OUT="$(realpath -m "$OUT")"
case "$OUT" in
  "$ROOT_REAL/out/"*) ;;
  *) die "output must be below $ROOT/out/: $OUT" ;;
esac
[ "$OUT" != "$ROOT_REAL/out" ] || die "refusing to use the whole out/ directory as output"
[ ! -L "$OUT" ] || die "refusing to use a symlink output: $OUT"

if [[ "$SRC_CACHE" != /* ]]; then
  SRC_CACHE="$ROOT/$SRC_CACHE"
fi
SRC_CACHE="$(realpath -m "$SRC_CACHE")"

BRANCH="$(git -C "$ROOT" branch --show-current)"
if [ "$BRANCH" != "feature/astro-native-platesolve" ]; then
  if [ "$BRANCH" = "main" ] && [ "$ALLOW_MAIN" = "1" ]; then
    echo "WARNING: development Astro build from main (--allow-main)"
  else
    die "controlled Astro builds must run on feature/astro-native-platesolve (got ${BRANCH:-detached}); use --allow-main only for a deliberate development build"
  fi
fi

TREE_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"
if [ -n "$TREE_STATUS" ] && [ "$ALLOW_DIRTY" != "1" ]; then
  echo "$TREE_STATUS" >&2
  die "source checkout is dirty; commit/stash it or pass --allow-dirty for a development build"
fi

git -C "$ROOT" diff --check || die "source whitespace errors detected"
command -v docker >/dev/null 2>&1 || die "docker is required by build-astro.sh"
docker info >/dev/null 2>&1 || die "docker daemon is not running"

if [ -n "$CATALOG_PACKAGE" ]; then
  if [[ "$CATALOG_PACKAGE" != /* ]]; then
    CATALOG_PACKAGE="$ROOT/$CATALOG_PACKAGE"
  fi
  CATALOG_PACKAGE="$(realpath -m "$CATALOG_PACKAGE")"
  [ -d "$CATALOG_PACKAGE/tiles" ] || die "catalogue package has no tiles/: $CATALOG_PACKAGE"
  for required in tiles.json tiles.ptri tiles.ptri.json; do
    [ -f "$CATALOG_PACKAGE/$required" ] || die "catalogue package is missing $required: $CATALOG_PACKAGE"
  done
fi

if [ -e "$OUT" ]; then
  [ "$FORCE" = "1" ] || die "output already exists: $OUT (use --force to replace this exact directory)"
  [ ! -L "$OUT" ] || die "refusing to remove a symlink output: $OUT"
  echo "[*] removing selected previous output: $OUT"
  rm -rf -- "$OUT"
fi

if [ "$RUN_TESTS" = "1" ]; then
  command -v python3 >/dev/null 2>&1 || die "python3 is required for the focused test gate"
  echo "[*] running focused Astro tests"
  python3 -m pytest -q \
    "$ROOT/container/astro/tests" \
    "$ROOT/tools/tests" \
    "$ROOT/tests/test_astro_build_wrapper.py"
  echo "[*] checking on-device shell syntax"
  for script in "$ROOT"/container/astro/ondisk/*.sh; do
    sh -n "$script"
  done
fi

HEAD="$(git -C "$ROOT" rev-parse HEAD)"
BUILD_ARGS=(--image "$IMAGE" --out "$OUT" --src-cache "$SRC_CACHE")
[ "$WANT_INDEXES" = "1" ] || BUILD_ARGS+=(--no-indexes)
[ -n "$CATALOG_PACKAGE" ] && BUILD_ARGS+=(--catalog-package "$CATALOG_PACKAGE")

echo "[*] building Astro bundle"
echo "    branch: $BRANCH"
echo "    commit: $HEAD"
echo "    output: $OUT"
echo "    indexes: $([ "$WANT_INDEXES" = "1" ] && echo enabled || echo disabled)"
echo "    catalogue: ${CATALOG_PACKAGE:-none}"
bash "$ROOT/build-astro.sh" "${BUILD_ARGS[@]}"

SD_ROOT="$OUT/COPY-TO-SD-CARD-ROOT"
SD_ASTRO="$SD_ROOT/polaris-astro"
[ -d "$SD_ASTRO" ] || die "build completed without COPY-TO-SD-CARD-ROOT/polaris-astro"
[ -x "$SD_ASTRO/polaris-solve" ] || die "bundle is missing native polaris-solve"
[ -x "$SD_ASTRO/polaris-solve-independent-search" ] || die "bundle is missing independent search solver"
[ -f "$SD_ASTRO/polaris-frame-watch.sh" ] || die "bundle is missing frame watcher"
[ -f "$OUT/licenses/README-GPL.txt" ] || die "bundle is missing corresponding-source notice"

MANIFEST="$OUT/ASTRO-MANIFEST.sha256"
(
  cd "$SD_ROOT"
  find . -type f -print0 | sort -z |
    while IFS= read -r -d '' file; do
      sha256sum "$file"
    done
) > "$MANIFEST"

PROVENANCE="$OUT/build-source-provenance.txt"
{
  echo "kind=astro-bundle"
  echo "build_id=$ID"
  echo "build_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "branch=$BRANCH"
  echo "patcher_commit=$HEAD"
  echo "source_tree_status=${TREE_STATUS:-clean}"
  echo "docker_image=$IMAGE"
  echo "indexes=$([ "$WANT_INDEXES" = "1" ] && echo enabled || echo disabled)"
  echo "catalogue_package=${CATALOG_PACKAGE:-none}"
  echo "firmware_release=not-produced"
  echo "firmware_flash=not-performed"
  printf 'command='
  printf '%q ' "$0" "${ORIGINAL_ARGS[@]}"
  printf '\n'
  echo "sd_tree_manifest=$(basename "$MANIFEST")"
  echo "tests=$([ "$RUN_TESTS" = "1" ] && echo passed || echo skipped)"
} > "$PROVENANCE"

AFTER_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)"
[ "$AFTER_STATUS" = "$TREE_STATUS" ] || die "build changed the source checkout"

echo
echo "Astro bundle ready: $OUT"
echo "Copy the CONTENTS of $SD_ROOT to the Polaris microSD root."
echo "No FwPkt was built, changed, or flashed."
echo "Manifest: $MANIFEST"
echo "Provenance: $PROVENANCE"
