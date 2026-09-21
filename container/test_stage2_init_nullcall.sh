#!/bin/sh
# Issue #124 regression test runner.
# Deterministic init-path tests: the #121 settle probe in
# stage2_pentax_enable_keep_live_view() must resolve (or safely skip)
# g_real_gp_widget_get_value before calling it during camera init.
set -eu

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_init_nullcall.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_init_nullcall" -ldl

"$work/test_stage2_init_nullcall"
