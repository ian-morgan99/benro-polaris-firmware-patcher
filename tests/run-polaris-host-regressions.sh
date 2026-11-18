#!/bin/sh
# SPDX-License-Identifier: MIT
# Host-only smoke regressions. No firmware, mount, camera or device needed.
set -eu
cd "$(dirname "$0")/.."
CC="${CC:-cc}"
TMP="${TMPDIR:-/tmp}/polaris-regression-$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
"$CC" -std=c99 -Wall -Wextra -Werror -pedantic -Icontainer/astro tests/test-polaris-job-token.c -o "$TMP/job-token"
"$TMP/job-token"
"$CC" -std=c99 -Wall -Wextra -Werror -pedantic -Icontainer/astro tests/test-polaris-image-pa.c -lm -o "$TMP/image-pa"
"$TMP/image-pa"
echo "host regression tests passed"
