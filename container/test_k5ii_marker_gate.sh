#!/bin/bash
# Regression coverage for issue #229: K-5 II and K-5 IIs markers are separate
# registrations. Prefix matching would accept a K-5 IIs-only camlib as K-5 II.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

marker_file="$tmp/legacy-pentax-markers.txt"
printf '%s\n' 'Pentax:K5IIs' > "$marker_file"

if grep -Fx -- 'Pentax:K5II' "$marker_file" >/dev/null; then
  echo "FAIL: K-5 IIs marker was accepted as K-5 II" >&2
  exit 1
fi
grep -Fx -- 'Pentax:K5IIs' "$marker_file" >/dev/null

grep -Fq 'grep -Fx -- "$model" "$LEGACY_MARKER_FILE"' \
  "$ROOT/container/patch.sh"
grep -Fq "grep -Fx -- 'Pentax:K5II'" \
  "$ROOT/container/test_polaris_pentax_build_package.sh"
grep -Fq "grep -Fx -- 'Pentax:K5IIs'" \
  "$ROOT/container/test_polaris_pentax_build_package.sh"

echo "[test_k5ii_marker_gate] PASS"
