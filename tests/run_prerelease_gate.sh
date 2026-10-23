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
DEVICE_LIBS=""
LIBGPHOTO2_SRC=""
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
        --device-libs)  DEVICE_LIBS="${2:?}"; shift 2 ;;
        --libgphoto2-src) LIBGPHOTO2_SRC="${2:?}"; shift 2 ;;
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

# Resolve a FUNCTIONAL ubireader_extract_files. A wrapper can be on PATH yet
# crash at import time (its Python module installed for a different interpreter),
# so `command -v` alone is not enough. Try the PATH candidate first, then the
# known-good /work/bin wrapper used by the native build runner; require --help
# to exit 0. Prints the chosen binary on stdout; non-zero exit if none works.
resolve_ubireader() {
    local c
    for c in "$(command -v ubireader_extract_files 2>/dev/null || true)" \
             /work/bin/ubireader_extract_files; do
        [ -n "$c" ] && [ -x "$c" ] || continue
        if "$c" --help >/dev/null 2>&1; then
            printf '%s\n' "$c"
            return 0
        fi
    done
    return 1
}

# Resolve a functional ARM objdump for the pgphoto timed-Bulb dispatch check.
# The cross-toolchain is often not on PATH (e.g. only under /run/host/usr/bin,
# where it also needs the host dynamic linker + lib paths). Probe PATH then the
# known host location; require --version to exit 0. Prints a runnable command:
# either the direct binary (PATH case) or a generated exec-wrapper (host case).
resolve_objdump() {
    local c probe
    for c in "$(command -v arm-linux-gnueabi-objdump 2>/dev/null || true)" \
             /run/host/usr/bin/arm-linux-gnueabi-objdump; do
        [ -n "$c" ] && [ -x "$c" ] || continue
        # Direct probe.
        if "$c" --version >/dev/null 2>&1; then
            printf '%s\n' "$c"; return 0
        fi
        # Host-binary case: needs the host dynamic linker + host lib paths.
        if [ -x /run/host/lib64/ld-linux-x86-64.so.2 ] && \
           LD_LIBRARY_PATH=/run/host/usr/lib/x86_64-linux-gnu:/run/host/lib/x86_64-linux-gnu \
               /run/host/lib64/ld-linux-x86-64.so.2 "$c" --version >/dev/null 2>&1; then
            probe="/tmp/prerelease-objdump-host.sh"
            {
                echo '#!/bin/sh'
                printf 'exec env LD_LIBRARY_PATH=/run/host/usr/lib/x86_64-linux-gnu:/run/host/lib/x86_64-linux-gnu /run/host/lib64/ld-linux-x86-64.so.2 %s "$@"\n' "$c"
            } > "$probe"
            chmod +x "$probe"
            printf '%s\n' "$probe"
            return 0
        fi
    done
    return 1
}

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
#    wire framing, canary file-check contract, capture-outcome classification and
#    shipped-artifact verification).
#    These encode the invariants of everything we believe is working; a new
#    regression must break one.
#
#    MAINTENANCE: this explicit list drifted once and five suites -- including
#    test_verify_installed_build.py, which is directly release-relevant -- went
#    unrun while the gate still reported GREEN. The list now lives in PY_TESTS below
#    and the drift guard fails the gate whenever a tests/test_*.py exists that is not
#    named there, so adding a suite forces a deliberate decision.
#
#    Every suite listed must be offline-safe: it may bind loopback and monkeypatch
#    socket.socket.connect, but must not require the Polaris. Device-dependent work
#    belongs in section 4, which is opt-in.
# ----------------------------------------------------------------------------
# Single source of truth: this array is what runs AND what the drift guard below
# checks against. An earlier version kept the list inline in the pytest invocation
# and re-extracted it with sed, which is fragile and was itself wrong once.
PY_TESTS=(
    tests/test_pentax_scenario_routing.py
    tests/test_pentax_stability_scenarios.py
    tests/test_pentax_stability_trace.py
    tests/test_canary_bulb.py
    tests/test_canary_two_shot.py
    tests/test_pentax_bulb_variations.py
    tests/test_astro_multishot.py
    tests/test_display_fwver_monotonic.py
    tests/test_agent_sandbox_check.py
    tests/test_agent_host_config_check.py
    tests/test_app_burst_protocol.py
    tests/test_canary_file_check.py
    tests/test_pull_mlog_clog.py
    tests/test_autonomous_install.py
    tests/test_assert_orphan_wrote.py
    tests/test_capture_outcomes.py
    tests/test_control_liveness.py
    tests/test_qualification_verdict.py
    tests/test_verify_installed_build.py
    tests/test_verify_shipped_artifacts.py
    tests/test_watch_app_crash.py
)

if python3 -m pytest -q "${PY_TESTS[@]}" > /tmp/prerelease-pytest.log 2>&1; then
    ok "python regression suite ($(grep -o '[0-9]* passed' /tmp/prerelease-pytest.log | tail -1))"
else
    bad "python regression suite (log: /tmp/prerelease-pytest.log)"
fi

# Drift guard: fail the gate when a tests/test_*.py exists that this array does not
# name. A suite nobody runs cannot catch a regression, and that is exactly how
# test_verify_installed_build.py sat unrun while this gate reported GREEN.
MISSING_TESTS="$(comm -13 \
    <(printf '%s\n' "${PY_TESTS[@]}" | sort) \
    <(ls tests/test_*.py 2>/dev/null | sort))"
if [ -n "$MISSING_TESTS" ]; then
    bad "python suites exist but are not run by this gate: $(printf '%s ' $MISSING_TESTS)"
    echo "      Add each to PY_TESTS above (offline-safe only) or delete the file."
else
    ok "python test-list drift guard (${#PY_TESTS[@]} suites, all listed)"
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

        # Immutable install manifest (issue #199): the post-reboot verify phase
        # compares every mandatory installed file's SHA-256 against this file.
        # It must exist for the candidate and its recorded zip digest must match
        # the current FwPkt.zip — a stale manifest would verify the wrong build.
        CAND_DIR="$(dirname "$BUILD")"
        if [ -f "$CAND_DIR/install-manifest.json" ]; then
            MZIP="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["zip"]["sha256"])' "$CAND_DIR/install-manifest.json" 2>/dev/null)"
            ZZIP="$(sha256sum "$CAND_DIR/FwPkt.zip" 2>/dev/null | cut -d' ' -f1)"
            if [ -n "$MZIP" ] && [ "$MZIP" = "$ZZIP" ]; then
                ok "install manifest present and current (zip sha256 matches $CAND_DIR)"
            else
                bad "install manifest stale or invalid (manifest=$MZIP zip=${ZZIP:-<missing>}; regenerate with scripts/generate-fwpkt-manifest.py)"
            fi
        else
            bad "install manifest missing for candidate ($CAND_DIR/install-manifest.json; run scripts/generate-fwpkt-manifest.py)"
        fi

        # Audit both the app-side request branch and pgphoto's concrete timed
        # Bulb dispatch in the exact repacked appfs.
        # Use a FUNCTIONAL ubireader (PATH first, then /work/bin); a broken
        # wrapper on PATH must not shadow a working one, and a missing/broken
        # tool is a prerequisite gap -> SKIP (never silent green).
        if UBI="$(resolve_ubireader)"; then
            PATCH_AUDIT_DIR="$(mktemp -d)"
            if "$UBI" -o "$PATCH_AUDIT_DIR" "$BUILD/camera/appfs.ubifs" \
                >/tmp/prerelease-appfs-extract.log 2>&1; then
                APP_BIN="$(find "$PATCH_AUDIT_DIR" -type f -path '*/bin/polestar_app' -print -quit)"
                if [ -n "$APP_BIN" ] && \
                   python3 container/polestar_bulb_patch.py "$APP_BIN" \
                       >/tmp/prerelease-polestar-bulb.log 2>&1; then
                    ok "polestar_app original Bulb branch intact in repacked appfs"
                else
                    bad "polestar_app contains a retired Bulb patch or unknown branch (log: /tmp/prerelease-polestar-bulb.log)"
                fi
                PGPHOTO_BIN="$(find "$PATCH_AUDIT_DIR" -type f -path '*/lib/stage2/pgphoto.stage2ondisk' -print -quit)"
                if [ -n "$PGPHOTO_BIN" ]; then
                    if OBJDUMP_BIN="$(resolve_objdump)"; then
                        if OBJDUMP="$OBJDUMP_BIN" python3 container/polaris_bulb_dispatch_patch.py "$PGPHOTO_BIN" --check \
                            >/tmp/prerelease-pgphoto-bulb.log 2>&1; then
                            ok "pgphoto timed Bulb dispatch present in repacked appfs"
                        else
                            bad "pgphoto timed Bulb dispatch missing or invalid (log: /tmp/prerelease-pgphoto-bulb.log)"
                        fi
                    else
                        skp "pgphoto timed Bulb dispatch check (no functional arm-linux-gnueabi-objdump on PATH or /run/host/usr/bin)"
                    fi
                else
                    # Machine-checkable predicate (issue #199): a SKIP for the
                    # pgphoto.stage2ondisk check is acceptable ONLY when the
                    # repacked appfs has no lib/stage2 tree at all (the
                    # candidate is not a full-libgphoto2 build, so the on-disk
                    # trampoline is nonmandatory). If lib/stage2 IS present but
                    # pgphoto.stage2ondisk is missing, the selected gate fails.
                    if [ -d "$PATCH_AUDIT_DIR/lib/stage2" ]; then
                        bad "pgphoto.stage2ondisk missing although appfs ships a lib/stage2 tree (mandatory for full-libgphoto2 candidates)"
                    else
                        skp "pgphoto timed Bulb dispatch check (no lib/stage2 tree in repacked appfs — stage2ondisk nonmandatory, machine-checked)"
                    fi
                fi
            else
                bad "appfs extraction for Bulb dispatch checks (log: /tmp/prerelease-appfs-extract.log)"
            fi
            rm -rf "$PATCH_AUDIT_DIR"
        else
            skp "polestar_app and pgphoto Bulb marker gates (no functional ubireader_extract_files on PATH or /work/bin)"
        fi
    fi
else
    echo "INFO: no --build given; package gates skipped (offline gate only)"
fi

# ----------------------------------------------------------------------------
# 3b. Shipped-artifact gates (#214 D1, D2).
#     The upstream regression suite runs against a meson build configured
#     -Dcamlibs=ptp2,pentax,directory, while the shipped libraries come from an
#     autotools build with --without-libxml-2.0 --without-jpeg --without-libcurl.
#     Same commit, different dependency graph, so those tests never exercise what
#     actually ships. Rather than reconciling the two configurations, assert the
#     artifact: every DT_NEEDED of every shipped .so must resolve inside the shipped
#     tree or from the device runtime, and the loader's compiled-in module directories
#     plus the manifest's mandatory paths must match the tree that was built.
#     Needs no device and no container runtime, so it runs whenever a build exists.
if [ -n "$BUILD" ]; then
    STAGE2_DIR="$(dirname "$BUILD")/stage2-ondisk"
    if [ ! -d "$STAGE2_DIR" ]; then
        # Some candidates stage the tree under the build dir itself.
        for cand in "$BUILD/../stage2-ondisk" "$BUILD/stage2-ondisk"; do
            [ -d "$cand" ] && STAGE2_DIR="$(cd "$cand" && pwd)" && break
        done
    fi
    if [ -d "$STAGE2_DIR" ]; then
        VERIFY_ARGS=("$STAGE2_DIR")
        if [ -n "$DEVICE_LIBS" ]; then
            if [ -f "$DEVICE_LIBS" ]; then
                VERIFY_ARGS+=(--device-libs "$DEVICE_LIBS")
            else
                bad "--device-libs file not found: $DEVICE_LIBS"
            fi
        else
            echo "INFO: no --device-libs given; using the built-in allowlist derived from a captured loader trace. Capture \`ls -1 /app/lib\` on the target for an authoritative reading."
        fi
        if [ -n "$LIBGPHOTO2_SRC" ] && [ -d "$LIBGPHOTO2_SRC" ]; then
            VERIFY_ARGS+=(--source "$LIBGPHOTO2_SRC")
        fi
        if python3 scripts/verify-shipped-artifacts.py "${VERIFY_ARGS[@]}" \
                > /tmp/prerelease-shipped-artifacts.log 2>&1; then
            ok "shipped .so dependencies and version pins"
        else
            bad "shipped .so dependencies or version pins (log: /tmp/prerelease-shipped-artifacts.log)"
            sed -n '1,20p' /tmp/prerelease-shipped-artifacts.log
        fi
    else
        skp "shipped .so dependency and version-pin gates (no stage2-ondisk tree beside $BUILD)"
    fi
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
if [ -z "$BUILD" ] && [ "$CANARY" != "1" ] && [ "$TWO_SHOT" != "1" ]; then
    echo "GATE: GREEN — OFFLINE-QUALIFIED only (no package/device gates ran)."
    echo "This is NOT device-qualified or release-qualified: the mandatory device install"
    echo "hash checks (scripts/o-v17a-autonomous-install.sh verify phase against the"
    echo "immutable install-manifest.json) and the physical Benro Connect / Manual / Bulb"
    echo "regression remain separate mandatory gates before a release is declared."
else
    echo "GATE: GREEN (skips, if any, are prerequisite gaps — record them in the release evidence)."
fi
exit 0
