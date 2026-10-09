#!/usr/bin/env bash
# Capture the exact moment Benro Connect dies, with the replies it was sent.
#
# Why: #187 asserts the app crashes on the NO-CAMERA state (`286 state:-5`).
# Measured on 2026-10-09 16:46 with the camera OFF, the app has an ESTABLISHED
# 9090 session from 192.168.0.2 and is stable, while the operator reports the
# crash happens when the camera is ON. So the trigger is the camera-present
# reply content, not its absence -- and we have never captured what the app is
# actually handed at that moment. Mlog.txt is only ~232 bytes and rotates, so
# reading it after the fact loses the crash.
#
# Streams three things into one timestamped file:
#   * device Mlog (SOCKET_ACCEPT/CLOSE, SP_SendMsgToApp payloads) via tail -F
#   * camera presence transitions (lsusb 25fb:*)
#   * the app's own startup query burst, replayed, so the replies the app chokes
#     on are recorded even when the app itself is too busy crashing to ask
set -u
HOST="${POLARIS_SSH:-root@192.168.0.1}"
OUT="${1:-/tmp/app-crash-watch.log}"
INTERVAL="${WATCH_INTERVAL:-5}"

ts() { date -u +%FT%TZ; }
log() { echo "$(ts) $*" >> "$OUT"; }

camera_present() {
    timeout 12 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" \
        'lsusb | grep -icE "05a9|25fb"' 2>/dev/null | tail -1
}

log "=== watch start (host=$HOST interval=${INTERVAL}s) ==="
prev="unknown"
while :; do
    cur=$(camera_present)
    [ -z "$cur" ] && cur="?"
    if [ "$cur" != "$prev" ]; then
        log "CAMERA_STATE change: $prev -> $cur"
        prev="$cur"
        # On the transition to present, snapshot exactly what the app will be
        # handed: the state queries from #187's Mlog plus the identity/storage
        # queries, and the device's own log from the moment of connect.
        if [ "$cur" = "1" ]; then
            log "--- app-burst replay (camera present) ---"
            timeout 90 python3 "$(dirname "$0")/app-burst.py" >> "$OUT" 2>&1
            log "--- device log ---"
            timeout 20 ssh -o BatchMode=yes "$HOST" \
                'tail -40 /app/Mlog.txt; echo "--- Clog ---"; tail -20 /app/Clog.txt' \
                >> "$OUT" 2>&1
        fi
    fi
    sleep "$INTERVAL"
done
