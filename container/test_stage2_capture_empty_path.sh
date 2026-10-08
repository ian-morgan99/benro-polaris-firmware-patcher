#!/bin/sh
# Issue #183 regression test runner.
# The guarded capture wrapper must convert GP_OK + empty CameraFilePath (the
# false-success signature behind the app "lockup") into GP_ERROR_CAMERA_ERROR,
# and pass every other case through untouched.
set -eu

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_capture_empty_path.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_capture_empty_path" -ldl

"$work/test_stage2_capture_empty_path"
