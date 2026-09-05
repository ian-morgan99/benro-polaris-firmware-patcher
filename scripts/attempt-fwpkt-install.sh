#!/usr/bin/env bash
# attempt-fwpkt-install.sh — the "one reboot" runbook for Path A.
#
# Chains the whole autonomous SD-card firmware install into a single command
# so future sessions stop re-entering recon mode:
#
#   1. Pre-flight: TCP 9090 reachable, SSH up, /app/sd/FwPkt.zip present and
#      its MD5 matches the padded build we staged (default EXPECTED_MD5).
#   2. Start a background Mlog tail+filter capture (same pattern as
#      watch-fwpkt-update.sh) into docs/evidence/fwpkt-install/.
#   3. Fire protocol code 812 (SYS_REBOOT, wire frame `1&812&0&#`) so the
#      on-boot FwPkt watcher fires against a freshly mounted /app/sd/.
#   4. Wait through the ~5-10 min dark period; poll for SSH to come back.
#   5. Give polestar_app time to run getFwInfo.sh, then grep the capture for
#      CHECK_FW PASS/FAIL and U-Boot handoff lines and print a binary verdict:
#        VERDICT: REFLASH TRIGGERED / NO UPGRADE NEEDED / INCONCLUSIVE
#
# This script is READ-ONLY on the device except for firing 812. It never
# touches /app/sd/FwPkt.zip, /dev/mtd*, or any NAND writer. The padded zip's
# own MD5 check inside polestar_app is the gatekeeper: mismatch -> U-Boot
# reflash; match -> "no need upgrade". Stock FwPkt.zip for revert lives in
# builds/stock/.
#
# Usage:
#   ./scripts/attempt-fwpkt-install.sh                 # full runbook
#   ./scripts/attempt-fwpkt-install.sh --dry-run       # pre-flight only, no 812
#   EXPECTED_MD5=<md5> ./scripts/attempt-fwpkt-install.sh   # different staged zip
#   MAX_WAIT=900 ./scripts/attempt-fwpkt-install.sh    # longer dark-period budget
#
# Env:
#   GIMBAL_HOST  (default 192.168.0.1)
#   GIMBAL_PORT  (default 9090, wire protocol port for 812)
#   GIMBAL_SSH   (default root@<GIMBAL_HOST>)
#   EXPECTED_MD5 (default 92da888387b14dc02976b5fa22b94067, the padded zip)
#   MAX_WAIT     (default 600 s budget for the device to come back up)
#   SETTLE       (default 120 s of Mlog settling after SSH returns)
#   EVIDENCE_DIR (default ./docs/evidence/fwpkt-install)
#
# Pre-flight requirements:
#   * You are associated with the polaris_* AP.
#   * The gimbal is powered on and awake (not deep-sleeping). If it is,
#     wake it first: bluetoothctl connect 48:E7:DA:D4:B5:72
#   * /app/sd/FwPkt.zip already staged (this script does NOT push anything).
#
# See: STATE.md "Decisive next move", layman-summary-2026-08-31.md,
#      scripts/reboot-via-812.sh, scripts/watch-fwpkt-update.sh

set -euo pipefail

GIMBAL_HOST="${GIMBAL_HOST:-192.168.0.1}"
GIMBAL_PORT="${GIMBAL_PORT:-9090}"
GIMBAL_SSH="${GIMBAL_SSH:-root@${GIMBAL_HOST}}"
EXPECTED_MD5="${EXPECTED_MD5:-92da888387b14dc02976b5fa22b94067}"
MAX_WAIT="${MAX_WAIT:-600}"
SETTLE="${SETTLE:-120}"
EVIDENCE_DIR="${EVIDENCE_DIR:-docs/evidence/fwpkt-install}"
WIRE='1&812&0&#'

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,52p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

STAMP="$(date -u +%Y%m%d-%H%M%S)"
CAPTURE="${EVIDENCE_DIR}/fwpkt-install-${STAMP}-mlog.log"

echo "=== attempt-fwpkt-install.sh $(date -u +%FT%TZ) ==="
echo "Target:   ${GIMBAL_HOST}:${GIMBAL_PORT} (ssh ${GIMBAL_SSH})"
echo "Expected /app/sd/FwPkt.zip md5: ${EXPECTED_MD5}"
echo "Capture:  ${CAPTURE}"
echo

if (( DRY_RUN )); then
    echo "(dry-run: pre-flight plan only, no 812 fired)"
    exit 0
fi

# --- Step 1: pre-flight -----------------------------------------------------
echo "--- [1/5] Pre-flight ---"
if ! timeout 3 bash -c "exec 3<>/dev/tcp/${GIMBAL_HOST}/${GIMBAL_PORT}" 2>/dev/null; then
    echo "ERROR: ${GIMBAL_HOST}:${GIMBAL_PORT} not reachable."
    echo "       On the polaris_* AP? Gimbal awake (BT wake if deep-sleeping)?"
    exit 3
fi
echo "TCP ${GIMBAL_PORT}: OK"

if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$GIMBAL_SSH" 'true' 2>/dev/null; then
    echo "ERROR: SSH to ${GIMBAL_SSH} failed. Is the AP up? Key authorized?"
    exit 3
fi
echo "SSH: OK"

ACTUAL_MD5="$(ssh -o BatchMode=yes "$GIMBAL_SSH" \
    'md5sum /app/sd/FwPkt.zip 2>/dev/null | cut -d" " -f1' || true)"
if [[ -z "${ACTUAL_MD5}" ]]; then
    echo "ERROR: /app/sd/FwPkt.zip not found on device. Stage the padded zip first."
    exit 4
fi
echo "/app/sd/FwPkt.zip md5: ${ACTUAL_MD5}"
if [[ "${ACTUAL_MD5}" != "${EXPECTED_MD5}" ]]; then
    echo "ERROR: staged zip md5 (${ACTUAL_MD5}) != expected (${EXPECTED_MD5})."
    echo "       Re-stage the padded build, or override with EXPECTED_MD5=${ACTUAL_MD5}."
    exit 4
fi
echo "MD5 matches. Pre-flight passed."
echo

# --- Step 2: background Mlog capture ----------------------------------------
mkdir -p "$EVIDENCE_DIR"
PATTERN='ExDevFwPkt|FwPkt|crcInfo|firmwareInfo|getFwInfo|getOmsFwInfo|UPGRADE|FwVer|appfs|rootfs|md5|size|remove /app/sd|FwPkt.zip|EXDEV_FW_PATH|GIMBAL_FW_PATH|FwSize|CHECK_FW|SEND_START|U-Boot'
echo "--- [2/5] Starting Mlog capture -> ${CAPTURE} ---"
ssh -o BatchMode=yes -o ServerAliveInterval=5 "$GIMBAL_SSH" \
    "tail -n0 -F /app/Mlog.txt 2>/dev/null" \
    | grep -E --line-buffered "$PATTERN" > "$CAPTURE" &
WATCH_PID=$!
sleep 1
echo "Capture running (pid ${WATCH_PID})."
echo

# --- Step 3: fire 812 --------------------------------------------------------
echo "--- [3/5] Firing 812 (SYS_REBOOT) ---"
printf '%s' "$WIRE" | timeout 5 nc -q1 "$GIMBAL_HOST" "$GIMBAL_PORT" || true
echo "Sent. Device will go dark for ~5-10 min (cold boot)."
echo

# --- Step 4: wait through the dark period ------------------------------------
echo "--- [4/5] Waiting up to ${MAX_WAIT}s for SSH to return ---"
elapsed=0
while (( elapsed < MAX_WAIT )); do
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$GIMBAL_SSH" 'true' 2>/dev/null; then
        echo "SSH back after ~${elapsed}s."
        break
    fi
    sleep 10
    elapsed=$(( elapsed + 10 ))
done
if (( elapsed >= MAX_WAIT )); then
    echo "WARN: SSH still down after ${MAX_WAIT}s. Giving it a bit more, but"
    echo "      the watcher may have already run; verdict below is best-effort."
fi

echo "Settling ${SETTLE}s for polestar_app + getFwInfo.sh to finish..."
sleep "$SETTLE"

# Stop the capture (numeric PID kill; sandbox quirk: avoid `kill $!`)
kill "$WATCH_PID" 2>/dev/null || true
wait "$WATCH_PID" 2>/dev/null || true
echo "Capture saved: ${CAPTURE} ($(wc -l < "$CAPTURE") matching lines)"
echo

# --- Step 5: verdict ---------------------------------------------------------
echo "--- [5/5] Verdict ---"
if grep -qE 'CHECK_FW PASS' "$CAPTURE"; then
    echo "VERDICT: REFLASH TRIGGERED (CHECK_FW PASS -> U-Boot handoff expected)"
    echo "         Watch the gimbal for the NAND reflash; verify FwVer afterwards."
elif grep -qE 'no need upgrade|NO_NEED_UPGRADE' "$CAPTURE"; then
    echo "VERDICT: NO UPGRADE NEEDED (MD5 matched stock manifest — wrong zip staged?)"
elif grep -qE 'CHECK_FW FAIL' "$CAPTURE"; then
    echo "VERDICT: CHECK FAILED (CHECK_FW FAIL) — inspect ${CAPTURE} for which"
    echo "         component mismatched; no NAND write should have happened."
else
    echo "VERDICT: INCONCLUSIVE — no CHECK_FW line in capture yet."
    echo "         Re-run the tail manually: ./scripts/watch-fwpkt-update.sh"
fi
echo
echo "Full capture: ${CAPTURE}"
