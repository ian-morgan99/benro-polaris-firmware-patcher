#!/bin/sh
# Generic Stage-2 config safety regression test.
set -eu
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_empty_choice_guard.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_empty_choice_guard" -ldl
"$work/test_stage2_empty_choice_guard"
