#!/usr/bin/env bash
# Compare the exact candidate identity with the running Polaris.
# This is intentionally separate from a canary: never capture on a device
# whose source/artifact/runtime identity has not first been proven.
set -euo pipefail

BUILD_DIR=""
HOST="192.168.0.1"
SSH_USER="root"

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --ssh-user) SSH_USER="$2"; shift 2 ;;
    -h|--help)
      echo "usage: $0 <build-dir> [--host IP] [--ssh-user USER]"; exit 0 ;;
    *)
      [ -z "$BUILD_DIR" ] || { echo "unexpected argument: $1" >&2; exit 2; }
      BUILD_DIR="$1"; shift ;;
  esac
done

[ -n "$BUILD_DIR" ] || { echo "usage: $0 <build-dir> [--host IP] [--ssh-user USER]" >&2; exit 2; }
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
[ -f "$BUILD_DIR/build-source-provenance.txt" ] || {
  echo "ERROR: candidate provenance missing: $BUILD_DIR/build-source-provenance.txt" >&2; exit 2;
}
[ -f "$BUILD_DIR/FwPkt/firmwareInfo" ] || {
  echo "ERROR: candidate FwPkt/firmwareInfo missing" >&2; exit 2;
}
[ -f "$BUILD_DIR/FwPkt/FwVer" ] || {
  echo "ERROR: candidate FwPkt/FwVer missing" >&2; exit 2;
}

SSH="${SSH_USER}@${HOST}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Checking running identity on $SSH against $BUILD_DIR"
ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH" 'test -x /app/bin/polestar_app && test -x /app/bin/pgphoto' || {
  echo "ERROR: target is not a Polaris runtime (polestar_app/pgphoto missing)" >&2; exit 3;
}
ssh -o BatchMode=yes "$SSH" 'cat /app/openpolaris-libgphoto2-provenance.txt' > "$TMP_DIR/device-provenance.txt"
ssh -o BatchMode=yes "$SSH" 'cat /app/FwVer' > "$TMP_DIR/device-fwver.txt"

# The astro kit is not part of appfs, so a correct FwVer says nothing about it.
# Fetch its stamp when the candidate carries a kit; absence on the device is a
# real finding, not an error to tolerate -- the Python side fails closed on it.
CANDIDATE_KIT="$BUILD_DIR/astro-bundle/COPY-TO-SD-CARD-ROOT/polaris-astro/VERSION"
KIT_ARGS=()
if [ -f "$CANDIDATE_KIT" ]; then
  KIT_ARGS+=(--candidate-kit-version "$CANDIDATE_KIT")
  if ssh -o BatchMode=yes "$SSH" 'test -f /app/sd/polaris-astro/VERSION' 2>/dev/null; then
    ssh -o BatchMode=yes "$SSH" 'cat /app/sd/polaris-astro/VERSION' > "$TMP_DIR/device-kit-version.txt"
    KIT_ARGS+=(--device-kit-version "$TMP_DIR/device-kit-version.txt")
  fi
fi

python3 "$(dirname "$0")/verify_installed_build.py" \
  --candidate-provenance "$BUILD_DIR/build-source-provenance.txt" \
  --device-provenance "$TMP_DIR/device-provenance.txt" \
  --candidate-fwver "$BUILD_DIR/FwPkt/FwVer" \
  --device-fwver "$TMP_DIR/device-fwver.txt" \
  "${KIT_ARGS[@]+"${KIT_ARGS[@]}"}"
