#!/bin/sh
# Issue #362 regression test runner.
#
# The loader must ask the driver for companions of a successful still capture and
# report them, because nothing else in the firmware stack ever does:
#   strings pgphoto.stage2ondisk | grep -c extra_capture  -> 0
#   strings libpolaris_stage2.so | grep -c extra_capture  -> 0
# Detection already works (companions=1 on dual-format captures); delivery does
# not, so a RAW is paid for and silently dropped and the client sees "RAW".
#
# The test binary exports gp_camera_get_extra_capture_files and is linked
# -rdynamic so the loader's dlsym(RTLD_DEFAULT, ...) resolves it, mirroring how
# it resolves the real symbol from libgphoto2.so.6 on the device.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM

cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_extra_capture_report.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -rdynamic -o "$work/test" -ldl

"$work/test" 2>"$work/trace"

# Cases 1 and 2 report companions; case 2 has two, so two per-file lines plus the
# summary line. Case 10 (count above the buffer) reports the honest count but
# prints only within the buffer.
grep -q 'extra-capture count=1 primary delivered but 1 companion' "$work/trace"
grep -q 'extra-capture count=2 primary delivered but 2 companion' "$work/trace"
grep -q 'extra-capture\[0\] folder=/store_00010001/DCIM name=IMGP0002_0.PEF' "$work/trace"
grep -q 'extra-capture\[1\] folder=/store_00010001/DCIM name=IMGP0002_1.PEF' "$work/trace"

# Case 10: count is reported honestly (13) but only STAGE2_EXTRA_MAX (8) entries
# are printed, so indices 0..7 appear and 8 does not.
grep -q 'extra-capture count=13' "$work/trace"
grep -q 'extra-capture\[7\]' "$work/trace"
if grep -q 'extra-capture\[8\]' "$work/trace"; then
    echo "FAIL: printed a companion beyond the buffer (would read out of bounds)"
    exit 1
fi

# Case 5: a query error is surfaced, never swallowed.
grep -q 'extra-capture-query=error ret=-1' "$work/trace"

# Case 4: GP_ERROR_NOT_SUPPORTED (-6) is the documented answer for a body without
# dual-format support and must NOT be logged as a failure.
if grep -q 'extra-capture-query=error ret=-6' "$work/trace"; then
    echo "FAIL: NOT_SUPPORTED logged as an error (normal for single-format bodies)"
    exit 1
fi

# Case 3: zero companions is a single-format capture and must be silent.
if grep -q 'extra-capture count=0' "$work/trace"; then
    echo "FAIL: reported a companion count of zero (single-format is normal)"
    exit 1
fi
