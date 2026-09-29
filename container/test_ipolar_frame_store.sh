#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CC="${CC:-cc}"
command -v "$CC" >/dev/null 2>&1 || {
    echo "SKIP: C compiler is unavailable" >&2
    exit 77
}
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ipolar-frame-store.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

"$CC" -std=c11 -Wall -Wextra -Werror -pthread \
    -I"$ROOT/container" \
    "$ROOT/container/test_ipolar_frame_store.c" \
    "$ROOT/container/stage2_ipolar_frames.c" \
    -o "$TMP/test-ipolar-frame-store"
"$TMP/test-ipolar-frame-store"
