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
#   ./tests/run_prerelease_gate.sh --canary --expected-files 1
#   ./tests/run_prerelease_gate.sh --two-shot --expected-files 2 \
#       --expected-sp-prefix /app/sd/normal/SP_
#   ./tests/run_prerelease_gate.sh --canary --expected-files 1 \
#       --bulb-seconds 30 --expected-sw 6.0.0.54.52
#   ./tests/run_prerelease_gate.sh --canary --expected-files 1 \
#       --expected-build-dir out/<candidate>
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
EXPECTED_FILES=""
EXPECTED_SP_PREFIX=""
BULB_SECONDS=""
BULB_INDEX=""
EXPECTED_SW=""
EXPECTED_BUILD_DIR=""
BULB_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --build)   BUILD="${2:?--build needs a path}"; shift 2 ;;
        --canary)  CANARY=1; shift ;;
        --two-shot) TWO_SHOT=1; shift ;;
        --host) HOST="${2:?}"; shift 2 ;;
        --port) PORT="${2:?}"; shift 2 ;;
        --bind) BIND="${2:?}"; shift 2 ;;
        --expected-files) EXPECTED_FILES="${2:?}"; shift 2 ;;
        --expected-sp-prefix) EXPECTED_SP_PREFIX="${2:?}"; shift 2 ;;
        --bulb-seconds) BULB_SECONDS="${2:?}"; shift 2 ;;
        --bulb-shutter-index) BULB_INDEX="${2:?}"; shift 2 ;;
        --expected-sw) EXPECTED_SW="${2:?}"; shift 2 ;;
        --expected-build-dir) EXPECTED_BUILD_DIR="${2:?}"; shift 2 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

if { [ "$CANARY" = "1" ] || [ "$TWO_SHOT" = "1" ]; } &&
   [ "$EXPECTED_FILES" != "1" ] && [ "$EXPECTED_FILES" != "2" ]; then
    echo "--canary/--two-shot requires --expected-files 1 or 2 from an independent mode contract" >&2
    exit 2
fi
if [ "$TWO_SHOT" = "1" ] && [ -z "$EXPECTED_SP_PREFIX" ]; then
    echo "--two-shot requires --expected-sp-prefix from the selected Polaris output target" >&2
    exit 2
fi
if [ -n "$BULB_SECONDS" ] && ! [[ "$BULB_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "--bulb-seconds must be a positive integer" >&2
    exit 2
fi
if [ -n "$BULB_INDEX" ] && ! [[ "$BULB_INDEX" =~ ^[0-9]+$ ]]; then
    echo "--bulb-shutter-index must be a non-negative integer" >&2
    exit 2
fi
if [ -n "$BULB_INDEX" ] && [ -z "$BULB_SECONDS" ]; then
    echo "--bulb-shutter-index requires --bulb-seconds" >&2
    exit 2
fi
if [ -n "$BULB_SECONDS" ] && [ "$CANARY" = "0" ] && [ "$TWO_SHOT" = "0" ]; then
    echo "--bulb-seconds requires --canary or --two-shot" >&2
    exit 2
fi
if [ -n "$EXPECTED_SW" ] && ! [[ "$EXPECTED_SW" =~ ^[0-9]+(\.[0-9]+){3,4}$ ]]; then
    echo "--expected-sw must be a four- or five-component numeric version" >&2
    exit 2
fi
if [ -n "$EXPECTED_SW" ] && [ "$CANARY" = "0" ] && [ "$TWO_SHOT" = "0" ]; then
    echo "--expected-sw requires --canary or --two-shot" >&2
    exit 2
fi
if [ -n "$EXPECTED_BUILD_DIR" ] && [ "$CANARY" = "0" ] && [ "$TWO_SHOT" = "0" ]; then
    echo "--expected-build-dir requires --canary or --two-shot" >&2
    exit 2
fi
if [ -n "$BULB_SECONDS" ]; then
    BULB_ARGS+=(--bulb-seconds "$BULB_SECONDS")
    if [ -n "$BULB_INDEX" ]; then
        BULB_ARGS+=(--bulb-shutter-index "$BULB_INDEX")
    fi
fi
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
#    trace tooling, Bulb variation matrix, astro multi-shot contract, app-burst
#    wire framing, and canary file-check contract).
#    These encode the invariants
#    of everything we believe is working; a new regression must break one.
# ----------------------------------------------------------------------------
if python3 -m pytest -q \
    tests/test_pentax_scenario_routing.py \
    tests/test_pentax_stability_scenarios.py \
    tests/test_pentax_stability_trace.py \
    tests/test_canary_bulb.py \
    tests/test_canary_two_shot.py \
    tests/test_pentax_bulb_variations.py \
    tests/test_astro_multishot.py \
    tests/test_display_fwver_monotonic.py \
    tests/test_agent_sandbox_check.py \
    tests/test_agent_host_config_check.py \
    tests/test_app_burst_protocol.py \
    tests/test_canary_file_check.py \
    tests/test_pull_mlog_clog.py \
    tests/test_watch_app_crash.py > /tmp/prerelease-pytest.log 2>&1; then
    ok "python regression suite ($(grep -o '[0-9]* passed' /tmp/prerelease-pytest.log | tail -1))"
else
    bad "python regression suite (log: /tmp/prerelease-pytest.log)"
fi

# ----------------------------------------------------------------------------
# 2b. Live agent-host checks (issues #184, #185). These run against THIS
#     host, not fixtures: the sandbox must be enabled AND functional (a
#     missing slirp4netns silently pushed every command outside the
#     sandbox), and the model pins must exist so selection is identical
#     whether chat.experimentalModelPicker is true or false. Exit 77 =
#     no VS Code-family settings here (e.g. CI container) = prerequisite
#     SKIP, never silent green. Contract: docs/AGENT-HOST-CONFIG.md.
# ----------------------------------------------------------------------------
for checker in scripts/check-agent-sandbox.py scripts/check-agent-host-config.py; do
    set --
    [ "$checker" = "scripts/check-agent-host-config.py" ] && \
        set -- --workspace-settings .vscode/settings.json
    if out="$(python3 "$checker" "$@" 2>&1)"; then
        ok "agent host check: $checker ($(printf '%s' "$out" | head -1))"
    else
        rc=$?
        if [ "$rc" = "77" ]; then
            skp "agent host check: $checker (no VS Code settings on this host)"
        else
            bad "agent host check: $checker (exit $rc) — $out"
        fi
    fi
done

# The code-780 version patch rewrites machine code inside polestar_app, so a
# defect in it is invisible to every Python test above. Four candidates shipped
# with the patch overwriting the instruction that sets the following memset's
# length, which corrupted device info while still reporting the right version.
# This check is a shell test on a synthetic image, so it must run even when no
# built package is supplied.
if sh container/test_polestar_fwver_patch.sh > /tmp/prerelease-fwver-patch.log 2>&1; then
    ok "code-780 version patch (exact copy, memset length preserved)"
else
    bad "code-780 version patch (log: /tmp/prerelease-fwver-patch.log)"
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

        # Verify that the repacked appfs retains the original Bulb branch and
        # does not contain the retired patch that zeroed bulb_ms.
        if command -v ubireader_extract_files >/dev/null 2>&1; then
            PATCH_AUDIT_DIR="$(mktemp -d)"
            if ubireader_extract_files -o "$PATCH_AUDIT_DIR" "$BUILD/camera/appfs.ubifs" \
                >/tmp/prerelease-polestar-extract.log 2>&1; then
                APP_BIN="$(find "$PATCH_AUDIT_DIR" -type f -path '*/bin/polestar_app' -print -quit)"
                if [ -n "$APP_BIN" ] && \
                   python3 container/polestar_bulb_patch.py "$APP_BIN" \
                       >/tmp/prerelease-polestar-bulb.log 2>&1; then
                    ok "polestar_app original Bulb branch intact in repacked appfs"
                else
                    bad "polestar_app contains a retired Bulb patch or unknown branch (log: /tmp/prerelease-polestar-bulb.log)"
                fi
            else
                bad "polestar_app appfs extraction for Bulb marker (log: /tmp/prerelease-polestar-extract.log)"
            fi
            rm -rf "$PATCH_AUDIT_DIR"
        else
            skp "polestar_app Bulb marker gate (ubireader_extract_files unavailable)"
        fi
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
        VERSION_GATE_OK=1
        if [ -n "$EXPECTED_BUILD_DIR" ]; then
            if scripts/verify-installed-build.sh "$EXPECTED_BUILD_DIR" --host "$HOST" > /tmp/prerelease-installed-build.log 2>&1; then
                ok "installed build identity"
            else
                bad "installed build identity (log: /tmp/prerelease-installed-build.log)"
                VERSION_GATE_OK=0
            fi
        fi
        if [ -n "$EXPECTED_SW" ]; then
            if python3 scripts/canary-probe.py --host "$HOST" --port "$PORT" --bind "$BIND" --probe \
                --expected-sw "$EXPECTED_SW" \
                > /tmp/prerelease-firmware-version.log 2>&1; then
                ok "code-780 firmware version ($EXPECTED_SW)"
            else
                bad "code-780 firmware version ($EXPECTED_SW; log: /tmp/prerelease-firmware-version.log)"
                VERSION_GATE_OK=0
            fi
        fi

        # Do not put the shutter through a candidate whose identity check has
        # failed.  This keeps a bad version response a red release check,
        # rather than allowing a later capture result to obscure it.
        if [ "$VERSION_GATE_OK" = "1" ]; then
            if [ "$CANARY" = "1" ]; then
                if python3 scripts/canary-probe.py --host "$HOST" --port "$PORT" --bind "$BIND" --shot \
                    --expected-files "$EXPECTED_FILES" \
                    "${BULB_ARGS[@]}" \
                    > /tmp/prerelease-canary-shot.log 2>&1; then
                    ok "canary shot (lifecycle + file event)"
                else
                    bad "canary shot (log: /tmp/prerelease-canary-shot.log)"
                fi
            fi
            if [ "$TWO_SHOT" = "1" ]; then
                if python3 scripts/canary-two-shot.py --host "$HOST" --port "$PORT" --bind "$BIND" \
                    --expected-files "$EXPECTED_FILES" \
                    --expected-sp-prefix "$EXPECTED_SP_PREFIX" \
                    "${BULB_ARGS[@]}" \
                    > /tmp/prerelease-twoshot.log 2>&1; then
                    ok "two-shot gate (two distinct files, fail-closed)"
                else
                    bad "two-shot gate (log: /tmp/prerelease-twoshot.log)"
                fi
            fi
        else
            skp "capture canary withheld after failed code-780 identity check"
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
