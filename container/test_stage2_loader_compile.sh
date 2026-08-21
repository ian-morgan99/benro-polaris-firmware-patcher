#!/bin/sh
set -eu

compiler="${1:-arm-linux-gnueabi-gcc}"
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
