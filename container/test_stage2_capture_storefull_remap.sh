#!/bin/sh
# Issue #181 follow-up regression test runner.
# The guarded capture wrapper must remap GP_ERROR_FIXED_LIMIT_EXCEEDED (-8,
# produced for PTP_RC_StoreFull 0x200c) onto GP_ERROR_NO_SPACE (-115), because
# pgphoto's capture_generic() only propagates an explicit allowlist of error
# codes and -8 is not on it -- so a full camera card was reported to the client
# as a successful capture with no file.  Codes already on that list must pass
# through byte-identical, and STAGE2_CAPTURE_STOREFULL_REMAP=0 must preserve the
# raw code.
set -eu

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

cc -O0 -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$(dirname "$0")" -I"$(dirname "$0")/testdata" \
    "$(dirname "$0")/test_stage2_capture_storefull_remap.c" \
    "$(dirname "$0")/stage2_policy.c" \
    -o "$work/test_stage2_capture_storefull_remap" -ldl

"$work/test_stage2_capture_storefull_remap"
