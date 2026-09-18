#!/bin/sh
set -eu

compiler="${1:-arm-linux-gnueabi-gcc}"
# Prerequisite: an ARM cross-compiler. When absent, signal SKIP (exit 77) so the
# aggregate harness (tests/run_deterministic.sh, issue #117) classifies this as
# unavailable rather than a real failure.
command -v "$compiler" >/dev/null 2>&1 || {
    echo "SKIP: $compiler not found (ARM cross-toolchain prerequisite)" >&2
    exit 77
}
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT HUP INT TERM

cp "$(dirname "$0")/stage2_loader.c" "$work/stage2_ondisk_loader.c"
cp "$(dirname "$0")/stage2_policy.c" "$(dirname "$0")/stage2_policy.h" "$work/"
cp "$(dirname "$0")/testdata/stage2_ondisk_table.h" "$work/"

"$compiler" -shared -fPIC -O2 -std=gnu11 -mfloat-abi=soft \
	-Wall -Wextra -Werror -Wl,-soname,libpolaris_stage2.so -I"$work" \
	"$work/stage2_ondisk_loader.c" "$work/stage2_policy.c" \
	-o "$work/libpolaris_stage2.so" -ldl
file "$work/libpolaris_stage2.so"

# Mirror patch.sh's provenance gate. Consume the complete strings output: under
# pipefail, grep -q can otherwise reject a present marker when strings gets
# SIGPIPE after grep's early exit.
strings "$work/libpolaris_stage2.so" |
	grep 'stage2_model_uses_r5_shims' >/dev/null
