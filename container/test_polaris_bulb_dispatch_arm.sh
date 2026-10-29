#!/bin/sh
# Release gate: actually execute the generated ARM code, including the widget
# pointer/lifetime and both cancellation outcomes. Missing emulator is a FAIL.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if ! python3 -c 'import unicorn' >/dev/null 2>&1; then
    echo 'FAIL: install Python unicorn to execute the Bulb dispatcher regression' >&2
    exit 1
fi
python3 -m pytest -q "$ROOT/container/test_polaris_bulb_dispatch_arm.py" \
    "$ROOT/container/test_qualification_round_bulb_block.py"
