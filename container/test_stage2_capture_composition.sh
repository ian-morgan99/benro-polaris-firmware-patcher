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
# Four trace-enabled combinations, three shots, six scenarios. Each call must
# log entry and the raw core return, including errors and converted outcomes.
[ "$(grep -c 'capture-enter' "$work/trace")" -eq 72 ]
[ "$(grep -c 'capture-return' "$work/trace")" -eq 72 ]
[ "$(grep -c 'capture-return.*ret=-10' "$work/trace")" -eq 12 ]
