#!/bin/sh
# Analysis-only host probe; not a release or physical-camera test.
set -eu
mode=${1:---require-protection}
case "$mode" in --observe|--require-protection) ;; *) exit 2 ;; esac
root=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
cc ${PROBE_CFLAGS:--O0} -std=gnu11 -Wall -Wextra -Werror \
    -Wno-unused-function -Wno-unused-variable \
    -I"$root/container" -I"$root/container/testdata" \
    "$root/docs/evidence/pentax-capture-recovery-20261008/capture-boundary-probe.c" \
    "$root/container/stage2_policy.c" -o "$work/probe" -ldl
"$work/probe" "$mode"
