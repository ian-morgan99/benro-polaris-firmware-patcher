#!/usr/bin/env bash
# resilient-monitor.sh
#
# Continuous, read-only monitor for the Benro Polaris gimbal that
# SURVIVES reboots, Wi-Fi drops, and extended dark periods. Built after
# the 2026-09-04/05 812-trigger attempt, where the device went dark for
# 60+ minutes and we had no continuous evidence trail across the gap
# (see STATE.md "Session log 2026-09-04/05").
#
# What it does, every poll cycle (default 5s):
#   1. Checks whether the host's Wi-Fi (wlp8s0) is associated to a
#      polaris_* AP (NOT just "is 192.168.0.1 pingable" -- that address
#      is NOT unique in this environment; see STATE.md gotcha).
#   2. If associated, checks whether SSH to the gimbal succeeds.
#   3. On every UP/DOWN transition, appends a timestamped line to the
#      timeline log.
#   4. Whenever SSH is up, captures a lightweight snapshot (uptime,
#      FwVer, boot id / dmesg boot line) into the same timeline log, so
#      we can reconstruct reboot history without ever sending a trigger.
#   5. Runs `tail -n0 -F /app/Mlog.txt` as a background sub-process
#      whenever SSH is up, appending everything to a single persistent
#      Mlog capture file (never truncated). If SSH drops, the tail dies
#      naturally; when SSH returns, a fresh tail is started (from the
#      new EOF) and appended to the SAME file, so the whole session's
#      Mlog history is queryable in one place, with clear GAP markers.
#
# This script is 100% read-only: no writes to /app/sd/, no triggers on
# port 9090, no reboot commands. Safe to leave running indefinitely.
#
# Usage:
#   ./scripts/resilient-monitor.sh
#   ./scripts/resilient-monitor.sh --once     # single snapshot, no loop
#
# Output:
#   docs/evidence/fwpkt-install/resilient-monitor-timeline.log   (UP/DOWN + snapshots)
#   docs/evidence/fwpkt-install/resilient-monitor-mlog.log       (append-only Mlog capture)
#
# Both logs are append-only across runs, so stopping/restarting this
# script does not lose history.

set -uo pipefail

GIMBAL_HOST="${GIMBAL_HOST:-192.168.0.1}"
WIFI_IFACE="${WIFI_IFACE:-wlp8s0}"
POLL_SECS="${POLL_SECS:-5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EVID_DIR="$REPO_ROOT/docs/evidence/fwpkt-install"
mkdir -p "$EVID_DIR"
TIMELINE="$EVID_DIR/resilient-monitor-timeline.log"
MLOG_CAP="$EVID_DIR/resilient-monitor-mlog.log"

ONCE=0
for arg in "$@"; do
    case "$arg" in
        --once) ONCE=1 ;;
        -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

ts() { date -u +%FT%TZ; }

log() {
    echo "[$(ts)] $*" | tee -a "$TIMELINE"
}

# Returns 0 if wlp8s0 is genuinely associated to a polaris_* AP right now.
is_associated() {
    nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null \
        | awk -F: -v ifc="$WIFI_IFACE" '$1==ifc && $2=="connected" {print $3}' \
        | grep -qi polaris
}

# Returns 0 if SSH batch-mode auth succeeds within a short timeout.
is_ssh_up() {
    timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new \
        "root@${GIMBAL_HOST}" true 2>/dev/null
}

MLOG_TAIL_PID=""

start_mlog_tail() {
    {
        echo "--- [$(ts)] Mlog tail (re)started ---"
        ssh -o BatchMode=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
            "root@${GIMBAL_HOST}" "tail -n0 -F /app/Mlog.txt 2>/dev/null"
    } >> "$MLOG_CAP" 2>&1 &
    MLOG_TAIL_PID=$!
}

stop_mlog_tail() {
    if [[ -n "$MLOG_TAIL_PID" ]] && kill -0 "$MLOG_TAIL_PID" 2>/dev/null; then
        kill "$MLOG_TAIL_PID" 2>/dev/null || true
        wait "$MLOG_TAIL_PID" 2>/dev/null || true
    fi
    MLOG_TAIL_PID=""
}

snapshot() {
    # Cheap, read-only facts. Never touches /app/sd/FwPkt or triggers anything.
    local uptime fwver bootline
    uptime=$(timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=4 "root@${GIMBAL_HOST}" \
        "cat /proc/uptime" 2>/dev/null | awk '{print $1}')
    fwver=$(timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=4 "root@${GIMBAL_HOST}" \
        "grep -a FwVer /app/*.ini /app/*.cfg 2>/dev/null | head -1" 2>/dev/null)
    bootline=$(timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=4 "root@${GIMBAL_HOST}" \
        "dmesg 2>/dev/null | head -1" 2>/dev/null)
    log "SNAPSHOT uptime=${uptime:-?}s fwver='${fwver:-?}' boot0='${bootline:-?}'"
}

trap 'stop_mlog_tail; log "monitor stopped (signal)"; exit 0' INT TERM

log "resilient-monitor.sh started (poll=${POLL_SECS}s host=${GIMBAL_HOST} iface=${WIFI_IFACE})"

STATE="UNKNOWN"

while true; do
    if is_associated && is_ssh_up; then
        if [[ "$STATE" != "UP" ]]; then
            log "STATE UP (associated + SSH reachable)"
            STATE="UP"
            snapshot
            start_mlog_tail
        fi
    else
        if [[ "$STATE" != "DOWN" ]]; then
            log "STATE DOWN (not associated or SSH unreachable)"
            STATE="DOWN"
            stop_mlog_tail
        fi
        # Actively rescan so we notice the AP the moment it reappears,
        # rather than waiting on NetworkManager's own background scan
        # cadence. Read-only: does not modify the gimbal, only the
        # host's Wi-Fi radio state.
        nmcli device wifi rescan ifname "$WIFI_IFACE" >/dev/null 2>&1 || true
    fi

    if (( ONCE )); then
        break
    fi
    sleep "$POLL_SECS"
done
