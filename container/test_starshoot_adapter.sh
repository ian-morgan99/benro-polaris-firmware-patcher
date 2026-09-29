#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
CC="${CC:-cc}"
command -v "$CC" >/dev/null 2>&1 || {
    echo "SKIP: C compiler is unavailable" >&2
    exit 77
}
TMP="$(mktemp -d "${TMPDIR:-/tmp}/starshoot-adapter.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

"$CC" -std=c11 -Wall -Wextra -Werror \
    -I"$ROOT/container/testdata/mock_libusb" -I"$ROOT/container" \
    "$ROOT/container/test_starshoot_adapter.c" \
    "$ROOT/container/stage2_starshoot_adapter.c" \
    -o "$TMP/test-starshoot-adapter"
"$TMP/test-starshoot-adapter"
