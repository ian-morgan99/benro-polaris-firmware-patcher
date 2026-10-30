#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
    "$root/container/stage2_config_receiver.c" -o "$work/receiver"
python3 "$root/container/test_stage2_config_receiver.py" "$work/receiver"
if command -v arm-linux-gnueabi-gcc >/dev/null 2>&1; then
    arm-linux-gnueabi-gcc -std=gnu11 -O2 -Wall -Wextra -Werror -mfloat-abi=soft \
        "$root/container/stage2_config_receiver.c" -o "$work/receiver-arm"
    file "$work/receiver-arm"
else
    echo 'SKIP: receiver ARM compile (cross-compiler absent); host tests passed'
fi
