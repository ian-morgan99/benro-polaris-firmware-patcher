#!/bin/sh
# Selection syntax and production-family floor must fail before Docker/input IO.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if "$ROOT/patch-polaris.sh" --fwpkt "$TMP" --camlibs '../ptp2' >"$TMP/bad.log" 2>&1; then
    echo "unsafe camlib token was accepted" >&2
    exit 1
fi
grep -F 'invalid --camlibs list' "$TMP/bad.log" >/dev/null

if "$ROOT/patch-polaris.sh" --fwpkt "$TMP" --camlibs pentax >"$TMP/missing.log" 2>&1; then
    echo "production selection without ptp2 was accepted" >&2
    exit 1
fi
grep -F 'production Polaris builds require ptp2' "$TMP/missing.log" >/dev/null

echo "camlib selection contract: PASS"
