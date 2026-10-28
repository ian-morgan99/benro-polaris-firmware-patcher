#!/usr/bin/env bash
# One-command reproducible candidate build and optional verified deployment.
#
# Usage:
#   ./scripts/release/build-and-install.sh                 # build only
#   ./scripts/release/build-and-install.sh --install       # build, wake, install
#   ./scripts/release/build-and-install.sh --install --wait 180
set -euo pipefail

ORIGINAL_ARGS=("$@")

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STOCK_FWPKT="${STOCK_FWPKT:-/home/ian/Documents/VSCodeProjects/PrivateResearch/openpolaris-research/BenroPolarisPatcher/firmware/FwPkt}"
LIBGPHOTO_REPO="${LIBGPHOTO_REPO:-https://github.com/ian-morgan99/libgphoto2.git}"
CANDIDATE_ID="${CANDIDATE_ID:-o-v18g-reproducible-$(date -u +%Y%m%d)}"
DISPLAY_FWVER="${DISPLAY_FWVER:-6.0.0.54.77}"
BUILD_ID="${BUILD_ID:-${DISPLAY_FWVER}-${CANDIDATE_ID}}"
INSTALL=0
WAIT_AP=120
SCAN=20

usage() {
  sed -n '2,12p' "$0"
  echo
  echo "Environment overrides: STOCK_FWPKT LIBGPHOTO_REPO CANDIDATE_ID DISPLAY_FWVER BUILD_ID"
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --install) INSTALL=1; shift;;
    --wait) WAIT_AP="$2"; shift 2;;
    --scan) SCAN="$2"; shift 2;;
    -h|--help) usage;;
    *) echo "ERROR: unknown option: $1" >&2; usage;;
  esac
done

# Always retain the complete terminal transcript, including early validation
# and Docker/host-route failures. The desktop launcher otherwise leaves the
# only useful diagnosis in a terminal that may already be closed.
LOG_DIR="$ROOT/out/$CANDIDATE_ID"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/build-and-install.log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== build-and-install $(date -u +%FT%TZ) ==="
echo "candidate=$CANDIDATE_ID display_fwver=$DISPLAY_FWVER install=$INSTALL"
trap 'rc=$?; echo "=== build-and-install finished $(date -u +%FT%TZ) rc=$rc ==="; exit "$rc"' EXIT

# VS Code may see the repository but not the host Docker CLI/socket.
if ! command -v docker >/dev/null 2>&1; then
  command -v flatpak-spawn >/dev/null 2>&1 || {
    echo "ERROR: Docker is unavailable and flatpak-spawn is not present." >&2
    exit 2
  }
  exec flatpak-spawn --host bash "$0" "${ORIGINAL_ARGS[@]}"
fi

docker info >/dev/null 2>&1 || {
  echo "ERROR: Docker CLI is present but the daemon is unavailable." >&2
  exit 2
}

[ "$(git -C "$ROOT" branch --show-current)" = main ] || {
  echo "ERROR: run this wrapper from the patcher main worktree." >&2
  exit 3
}
[ "$(git -C "$ROOT" status --porcelain)" = "" ] || {
  echo "ERROR: patcher main is dirty; commit or stash before release." >&2
  exit 3
}
[ -f "$STOCK_FWPKT/FwPkt/firmwareInfo" ] || {
  echo "ERROR: stock base not found: $STOCK_FWPKT/FwPkt/firmwareInfo" >&2
  exit 2
}

TMP_SRC="$(mktemp -d /tmp/libgphoto2-release.XXXXXX)"
cleanup() {
  rc=$?
  rm -rf "$TMP_SRC"
  echo "=== build-and-install finished $(date -u +%FT%TZ) rc=$rc ==="
  return "$rc"
}
trap cleanup EXIT

echo "== clean libgphoto2 source =="
git clone --branch main --single-branch "$LIBGPHOTO_REPO" "$TMP_SRC"

echo "== build candidate $CANDIDATE_ID ($DISPLAY_FWVER) =="
"$ROOT/scripts/build-release-candidate.sh" \
  "$CANDIDATE_ID" "$STOCK_FWPKT" "$TMP_SRC" "$BUILD_ID" "$DISPLAY_FWVER"

BUILD_DIR="$ROOT/out/$CANDIDATE_ID"
if [ "$INSTALL" -eq 0 ]; then
  echo "Build complete. Review and commit the release-state diff, then deploy with:"
  echo "  $ROOT/scripts/polaris-preflight.sh --wake --wait 120 --scan 20"
  echo "  $ROOT/scripts/release/release-fwpkt.sh $BUILD_DIR"
  exit 0
fi

echo "== host-aware Polaris preflight and Bluetooth wake =="
"$ROOT/scripts/polaris-preflight.sh" --wake --wait "$WAIT_AP" --scan "$SCAN"

echo "== verified extracted-tree deployment =="
"$ROOT/scripts/release/release-fwpkt.sh" "$BUILD_DIR"

echo "Deployment complete. Hardware qualification remains a separate gate."
