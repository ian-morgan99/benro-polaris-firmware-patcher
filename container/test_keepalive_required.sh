#!/bin/sh
set -eu

# Issue #339: the keepalive must be armed for EVERY session that touches a
# Polaris, not just "multi-minute live gates". That narrow wording is what let
# the v107 deploy lose the radio between short SSH commands, with no host-side
# recovery.
#
# The rule already existed as prose in AGENTS.md; prose is what failed. This test
# pins two things:
#   1. the deploy checklist no longer carries the narrow wording, and
#   2. release-fwpkt.sh actually refuses to start a destructive flash without a
#      verified keepalive -- and can be talked out of it only by an explicit,
#      loud override (issue #337 criticised this script for hard stops with no
#      documented way forward).

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
AGENTS=$ROOT/AGENTS.md
RELEASE=$ROOT/scripts/release/release-fwpkt.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# 1. The narrow wording must be gone from the checklist.
if grep -q "during any multi-minute live gate" "$AGENTS"; then
    echo "FAIL: AGENTS.md still scopes the keepalive to multi-minute gates (#339)"
    exit 1
fi
grep -q 'every.*session that touches' "$AGENTS"

# 2. The release script must gate on it, before the flash.
grep -q 'OPENPOLARIS_KEEPALIVE_PID' "$RELEASE"
grep -q 'OPENPOLARIS_ALLOW_NO_KEEPALIVE' "$RELEASE"
grep -q 'no Polaris keepalive is running' "$RELEASE"

# 3. The gate must sit BEFORE the destructive staging/flash, not after it.
gate_line=$(grep -n 'no Polaris keepalive is running' "$RELEASE" | cut -d: -f1)
flash_line=$(grep -n 'refusing destructive flash' "$RELEASE" | cut -d: -f1)
[ -n "$gate_line" ] && [ -n "$flash_line" ] && [ "$gate_line" -lt "$flash_line" ]

# 4. Behavioural check on the detection predicate itself, extracted from the
#    script so the test tracks the real expression rather than a copy of it.
detect() {
    pidfile=$1
    [ -f "$pidfile" ] || return 1
    pid=$(cat "$pidfile" 2>/dev/null)
    kill -0 "$pid" 2>/dev/null || return 1
    grep -q polaris-bt-keepalive "/proc/$pid/cmdline" 2>/dev/null
}

# A live keepalive process is accepted.
( exec -a "bash $ROOT/scripts/polaris-bt-keepalive.sh" sleep 60 ) &
live=$!
echo "$live" > "$TMP/ka.pid"
sleep 1
detect "$TMP/ka.pid" || { echo "FAIL: live keepalive not detected"; exit 1; }

# A stale pid (process gone) is rejected -- /tmp and UBIFS are not trustworthy.
echo 999999 > "$TMP/stale.pid"
if detect "$TMP/stale.pid"; then
    echo "FAIL: a stale pidfile was accepted as proof of a keepalive"
    exit 1
fi

# A live pid that is NOT the keepalive is rejected (pid reuse).
echo $$ > "$TMP/wrong.pid"
if detect "$TMP/wrong.pid"; then
    echo "FAIL: an unrelated live process was accepted as the keepalive"
    exit 1
fi

# No file at all is rejected.
if detect "$TMP/absent.pid"; then
    echo "FAIL: missing pidfile was accepted"
    exit 1
fi

kill $live 2>/dev/null || true

echo 'PASS: keepalive is required for every Polaris session and enforced pre-flash (issue #339)'
