#!/usr/bin/env bash
# ============================================================================
# PRE-RELEASE GATE — deterministic, coded regression gate for Benro Polaris.
#
# Purpose: anything we believe is currently working gets a coded regression
# test here so releases are verified by script output, not AI interpretation.
# Run this BEFORE staging a FwPkt.zip to the SD card and before declaring a
# release ready. It is fail-closed: any runnable check that fails turns the
# gate red; missing prerequisites are reported as SKIP (never silent green).
#
# Usage:
#   ./tests/run_prerelease_gate.sh                 # all offline checks
#   ./tests/run_prerelease_gate.sh --build out/<name>/FwPkt   # + package gates
#   ./tests/run_prerelease_gate.sh --canary        # + live canary (camera ON)
#   ./tests/run_prerelease_gate.sh --two-shot      # + two-shot gate (camera ON)
#   ./tests/run_prerelease_gate.sh --host 192.168.0.1 --port 9090 --bind 192.168.0.4
#
# Exit codes: 0 = gate green (skips allowed), 1 = a runnable check failed,
# 2 = usage error.
# ============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BUILD=""
CANARY=0
TWO_SHOT=0
HOST="192.168.0.1"
PORT="9090"
BIND="192.168.0.4"

while [ $# -gt 0 ]; do
    case "$1" in
        --build)   BUILD="${2:?--build needs a path}"; shift 2 ;;
        --canary)  CANARY=1; shift ;;
        --two-shot) TWO_SHOT=1; shift ;;
        --host) HOST="${2:?}"; shift 2 ;;
        --port) PORT="${2:?}"; shift 2 ;;
        --bind) BIND="${2:?}"; shift 2 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

pass=0; fail=0; skip=0
failed=""; skipped=""

ok()   { pass=$((pass+1)); echo "PASS: $1"; }
bad()  { fail=$((fail+1)); failed="$failed $1"; echo "FAIL: $1"; }
skp()  { skip=$((skip+1)); skipped="$skipped $1"; echo "SKIP: $1 (prerequisite unavailable)"; }

echo "=== Polaris pre-release gate ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

# ----------------------------------------------------------------------------
# 1. Deterministic container regression harness (patch/patcher behaviour).
#    Exit policy: runnable failure -> red; exit 2/77 = prerequisite skip.
# ----------------------------------------------------------------------------
if bash tests/run_deterministic.sh > /tmp/prerelease-deterministic.log 2>&1; then
    ok "container deterministic harness ($(grep -o '[0-9]* passed' /tmp/prerelease-deterministic.log | tail -1))"
else
    rc=$?
    if [ "$rc" = "2" ] || [ "$rc" = "77" ]; then
        skp "container deterministic harness"
    else
        bad "container deterministic harness (exit $rc; log: /tmp/prerelease-deterministic.log)"
    fi
fi

# ----------------------------------------------------------------------------
# 2. Coded Python regression tests (scenario routing, stability catalogue,
#    trace tooling, astro multi-shot contract). These encode the invariants
#    of everything we believe is working; a new regression must break one.
# ----------------------------------------------------------------------------
if python3 -m pytest -q \
    tests/test_pentax_scenario_routing.py \
    tests/test_pentax_stability_scenarios.py \
    tests/test_pentax_stability_trace.py \
    tests/test_astro_multishot.py > /tmp/prerelease-pytest.log 2>&1; then
    ok "python regression suite ($(grep -o '[0-9]* passed' /tmp/prerelease-pytest.log | tail -1))"
else
    bad "python regression suite (log: /tmp/prerelease-pytest.log)"
fi

# ----------------------------------------------------------------------------
# 3. FwPkt package gates — only when a built package is supplied.
#    a) structural validation (layout, duplicates, stock SHA-256 cross-check)
#    b) firmwareInfo manifest self-consistency vs the STOCK manifest
#       (the on-board crcInfo gate: any mismatch = silent no-op install)
# ----------------------------------------------------------------------------
if [ -n "$BUILD" ]; then
    if [ ! -e "$BUILD" ]; then
        bad "build path not found: $BUILD"
    else
        if python3 container/validate_fw_package.py "$BUILD" > /tmp/prerelease-validate.log 2>&1; then
            ok "FwPkt structural validation ($BUILD)"
        else
            bad "FwPkt structural validation (log: /tmp/prerelease-validate.log)"
        fi

        STOCK_FI="$(mktemp)"
        if python3 -c "
import sys, zipfile
try:
    data = zipfile.ZipFile('firmware/FwPkt.zip').read('FwPkt/firmwareInfo')
except Exception as e:
    print(f'stock manifest unavailable: {e}', file=sys.stderr); sys.exit(1)
open('$STOCK_FI','wb').write(data)
" 2>/dev/null; then
            if python3 container/verify_firmwareinfo.py "$STOCK_FI" "$BUILD" > /tmp/prerelease-firmwareinfo.log 2>&1; then
                ok "firmwareInfo manifest gate (stock manifest vs $BUILD)"
            else
                bad "firmwareInfo manifest gate (log: /tmp/prerelease-firmwareinfo.log)"
            fi
        else
            skp "firmwareInfo manifest gate (no stock firmware/FwPkt.zip in repo)"
        fi
        rm -f "$STOCK_FI"
    fi
else
    echo "INFO: no --build given; package gates skipped (offline gate only)"
fi

# ----------------------------------------------------------------------------
# 4. Live device gates — only when requested AND the Polaris is reachable.
#    Camera must be ON and attached for these (see AGENTS.md canary rule).
#    The probe first checks reachability so a powered-off gimbal reports SKIP,
#    not FAIL.
# ----------------------------------------------------------------------------
if [ "$CANARY" = "1" ] || [ "$TWO_SHOT" = "1" ]; then
    if python3 scripts/canary-probe.py --host "$HOST" --port "$PORT" --bind "$BIND" --probe \
        > /tmp/prerelease-canary-probe.log 2>&1 && grep -q "state=1" /tmp/prerelease-canary-probe.log; then
        ok "canary probe (device reachable, camera state=1)"
        if [ "$CANARY" = "1" ]; then
            if python3 scripts/canary-probe.py --host "$HOST" --port "$PORT" --bind "$BIND" --shot \
                > /tmp/prerelease-canary-shot.log 2>&1; then
                ok "canary shot (lifecycle + file event)"
            else
                bad "canary shot (log: /tmp/prerelease-canary-shot.log)"
            fi
        fi
        if [ "$TWO_SHOT" = "1" ]; then
            if python3 scripts/canary-two-shot.py --host "$HOST" --port "$PORT" --bind "$BIND" \
                > /tmp/prerelease-twoshot.log 2>&1; then
                ok "two-shot gate (two distinct files, fail-closed)"
            else
                bad "two-shot gate (log: /tmp/prerelease-twoshot.log)"
            fi
        fi
    else
        skp "live device gates (probe failed or camera state!=1 — gimbal off / camera not attached; log: /tmp/prerelease-canary-probe.log)"
    fi
fi

# ----------------------------------------------------------------------------
# Summary. Green gate = zero runnable failures; skips are reported, never
# silently green.
# ----------------------------------------------------------------------------
echo "=== Pre-release gate summary: ${pass} passed, ${fail} failed, ${skip} skipped ==="
[ -n "$skipped" ] && echo "Skipped:${skipped}"
[ -n "$failed" ] && echo "Failed:${failed}"
if [ "$fail" -gt 0 ]; then
    echo "GATE: RED — do not stage/install the FwPkt until the failed checks pass."
    exit 1
fi
echo "GATE: GREEN (skips, if any, are prerequisite gaps — record them in the release evidence)."
exit 0
