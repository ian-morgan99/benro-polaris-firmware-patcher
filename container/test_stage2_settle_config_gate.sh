#!/bin/sh
# Issue #121 regression test runner: the preview-settle window must gate
# config/status traffic (set_config, set_single_config) as well as preview.
set -eu
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_settle_config_gate.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_settle_config_gate" -ldl
"$work/test_stage2_settle_config_gate"
