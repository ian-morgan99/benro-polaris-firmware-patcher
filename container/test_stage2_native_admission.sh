#!/bin/sh
set -eu
cd "$(dirname "$0")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cc -O2 -std=c11 -Wall -Wextra -Werror test_stage2_policy.c stage2_policy.c -o "$work/policy"
"$work/policy"
cc -O2 -std=gnu11 -Wall -Wextra -Werror -Wno-unused-variable -Wno-unused-function \
    -Itestdata test_stage2_native_admission.c stage2_policy.c -o "$work/admission" -pthread -ldl
"$work/admission"
