#!/bin/sh
# Automatically discovered by tests/run_deterministic.sh.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc ${COMPOSITION_CFLAGS:--O0} -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_capture_composition.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test" -ldl
"$work/test" 2>"$work/trace"
# Eight trace-enabled combinations (trace on, other three modes free), three
# shots, seven scenarios. Each call must log entry and the RAW core return,
# including errors and converted outcomes.
[ "$(grep -c 'capture-enter' "$work/trace")" -eq 168 ]
[ "$(grep -c 'capture-return' "$work/trace")" -eq 168 ]
[ "$(grep -c 'capture-return.*ret=-10' "$work/trace")" -eq 24 ]
# Scenario 6 returns -8 from the core. The trace must still show -8 even when
# the wrapper converts it to -115, so a reader can tell what the core actually
# did rather than only what pgphoto was handed.
[ "$(grep -c 'capture-return.*ret=-8 ' "$work/trace")" -eq 24 ]
[ "$(grep -c 'wait-event.*requested_ms=3000' "$work/trace")" -eq 2 ]
