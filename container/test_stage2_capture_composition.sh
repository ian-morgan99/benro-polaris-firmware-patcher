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
# Sixteen trace-enabled combinations (trace on, the other four modes free),
# three shots, seven scenarios. Each call must log entry and the RAW core
# return, including errors and converted outcomes.
#   2^4 = 16 combos with trace on -> 16 * 3 * 7 = 336 calls
# (was 2^3 = 8 -> 168 before issue #362 added companion reporting as a fifth
# mode; if you add a sixth mode, double these again.)
[ "$(grep -c 'capture-enter' "$work/trace")" -eq 336 ]
[ "$(grep -c 'capture-return' "$work/trace")" -eq 336 ]
# One scenario per shot returns -10: 16 * 3 = 48.
[ "$(grep -c 'capture-return.*ret=-10' "$work/trace")" -eq 48 ]
# Scenario 6 returns -8 from the core. The trace must still show -8 even when
# the wrapper converts it to -115, so a reader can tell what the core actually
# did rather than only what pgphoto was handed.
[ "$(grep -c 'capture-return.*ret=-8 ' "$work/trace")" -eq 48 ]
[ "$(grep -c 'wait-event.*requested_ms=3000' "$work/trace")" -eq 2 ]
# Companion reporting must not emit anything when the core has no
# gp_camera_get_extra_capture_files symbol: a missing symbol is normal on older
# cores, and noise on every capture would make the log useless.
[ "$(grep -c 'extra-capture' "$work/trace")" -eq 0 ]
