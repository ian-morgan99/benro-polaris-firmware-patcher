#!/bin/sh
# Issue #187 SHIM #6 regression test runner: the gp_camera_get_single_config
# shutter-fallback must only return success with a complete value-bearing
# synthetic widget; on any helper failure it frees the widget and propagates
# the original camera error (fail-closed).
set -eu
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_shutter_fallback.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_shutter_fallback" -ldl
"$work/test_stage2_shutter_fallback"
