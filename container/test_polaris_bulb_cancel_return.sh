#!/bin/sh
# Release blocker for the unfinished K-3 III cancel/stop path.  The audit uses
# the exact v90 binary only as an immutable offline reference; no device is used.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -z "${POLARIS_V90_PGPHOTO:-}" ] || [ ! -r "$POLARIS_V90_PGPHOTO" ]; then
    echo 'FAIL: set POLARIS_V90_PGPHOTO to the exact v90 pgphoto binary for the mandatory cancellation-return test' >&2
    exit 1
fi
if ! python3 -c 'import unicorn, elftools' >/dev/null 2>&1; then
    echo 'FAIL: the cancellation-return test requires Python unicorn and pyelftools' >&2
    exit 1
fi
python3 "$ROOT/tools/audit_polaris_bulb_cancel.py" "$POLARIS_V90_PGPHOTO"
