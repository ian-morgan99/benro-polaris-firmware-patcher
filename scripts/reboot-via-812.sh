#!/usr/bin/env bash
# reboot-via-812.sh
#
# Trigger a cold reboot of the Benro Polaris gimbal by sending protocol
# code 812 (SYS_REBOOT) over TCP 9090. This is the same wire-level
# command the iPhone/Android Benro Connect app issues when you pick
# "Reboot" in its settings, and is the documented benign way to cycle
# polestar_app -- cleaner than `kill 248` because:
#
#   * U-Boot fully reinitialises, so /app/sd/ is re-mounted cleanly
#   * No risk of leaving a child process holding port 9090 in TIME_WAIT
#   * No risk of half-killing polestar_app mid-state-machine
#   * The on-boot FwPkt watcher (SP_OmsUpgradeFromSd) is guaranteed
#     to fire against the freshly mounted SD card
#
# Wire format (from Codes.kt + CommandTable.kt in OpenPolaris):
#   1&<code>&<subtype>&<payload>#
# For 812:  1&812&0&#
# Live verified response:  ret:0;
# followed by the device going dark for ~5-10 minutes (cold boot).
#
# Safety:
#   * Read-only with respect to /app/sd/FwPkt.zip. We never touches it.
#   * Does not flash any NAND. The padded FwPkt's own MD5 check is the
#     gatekeeper for whether the on-boot watcher proceeds to U-Boot
#     handoff. Failed check = no overwrite.
#   * Stock FwPkt.zip is available at builds/stock/ for revert.
#
# Usage:
#   ./scripts/reboot-via-812.sh                # fire 812, no prompt
#   ./scripts/reboot-via-812.sh --dry-run      # just print the wire frame
#   ./scripts/reboot-via-812.sh --watch        # also tail Mlog.txt live
#
# Pre-flight:
#   * You must be associated with the polaris_* AP.
#   * The gimbal must be powered on and awake (ping 192.168.0.1 OK).
#   * /app/sd/FwPkt.zip must already be in place (this script does
#     NOT push anything).
#
# See: layman-summary-2026-08-31.md, STATE.md TL;DR

set -euo pipefail

GIMBAL_HOST="${GIMBAL_HOST:-192.168.0.1}"
GIMBAL_PORT="${GIMBAL_PORT:-9090}"
WIRE='1&812&0&#'

DRY_RUN=0
WATCH=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --watch)   WATCH=1 ;;
        -h|--help)
            sed -n '2,42p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown arg: $arg" >&2
            exit 2
            ;;
    esac
done

echo "=== reboot-via-812.sh $(date -u +%FT%TZ) ==="
echo "Target: ${GIMBAL_HOST}:${GIMBAL_PORT}"
echo "Wire:   ${WIRE}"
echo

if (( DRY_RUN )); then
    echo "(dry-run: not sending)"
    exit 0
fi

# Sanity check: is the gimbal reachable on TCP 9090?
if ! timeout 3 bash -c "exec 3<>/dev/tcp/${GIMBAL_HOST}/${GIMBAL_PORT}" 2>/dev/null; then
    echo "ERROR: ${GIMBAL_HOST}:${GIMBAL_PORT} not reachable."
    echo "       Are you on the polaris_* AP? Is the gimbal awake?"
    exit 3
fi

# Optionally start Mlog tail in background before we fire
WATCH_PID=""
if (( WATCH )); then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -x "$SCRIPT_DIR/watch-fwpkt-update.sh" ]]; then
        echo "Starting Mlog tail in background..."
        "$SCRIPT_DIR/watch-fwpkt-update.sh" \
            > "/tmp/reboot-812-mlog-$(date -u +%H%M%S).log" 2>&1 &
        WATCH_PID=$!
        sleep 1
    else
        echo "WARN: watch-fwpkt-update.sh not found; skipping --watch"
    fi
fi

# Fire 812
echo "Sending 812..."
printf '%s' "$WIRE" | timeout 5 nc -q1 "$GIMBAL_HOST" "$GIMBAL_PORT" || true
echo
echo "Sent. Expected: ret:0;  (or no reply if device drops immediately on reboot)."

if [[ -n "$WATCH_PID" ]]; then
    echo
    echo "Mlog tail running in background (pid $WATCH_PID)."
    echo "It will capture new lines as polestar_app restarts."
    echo "When SSH comes back (~5-10 min), check the log for SP_OmsUpgradeFromSd, FwPkt, MD5, etc."
    echo
    echo "To stop the tail:  kill $WATCH_PID"
fi

echo
echo "=== Done. Watch the gimbal. SSH will drop and come back when boot completes. ==="
