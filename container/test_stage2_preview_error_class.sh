#!/bin/sh
# Issue #127 regression test runner: preview governor classifies error classes.
set -eu
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_preview_error_class.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_preview_error_class" -ldl
"$work/test_stage2_preview_error_class"
