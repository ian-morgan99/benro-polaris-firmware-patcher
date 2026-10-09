#!/usr/bin/env bash
# Capture device-side evidence around Benro Connect's camera-present failure.
#
# Mlog from the last attempt showed the important trap: the automatic app-burst
# replay was App[105] from the host, while the native phone did not reconnect
# until several minutes later. The replay queried before Pentax initialization
# completed and observed state:-5; it was not proof of what Benro Connect saw.
# Therefore snapshot native socket/Mlog/Clog state immediately on the USB
# transition, BEFORE any optional separate diagnostic replay. Replay is now
# opt-in with WATCH_REPLAY=1 so the default run does not add 9090 traffic.
#
# No capture/shutter command is sent by this watcher. Output is one timestamped
# host-side file containing camera USB transitions and separately labeled
# pre-replay, optional replay, and post-replay evidence.
set -u
HOST="${POLARIS_SSH:-root@192.168.0.1}"
GIMBAL_IP="${POLARIS_IP:-192.168.0.1}"
WIFI_IFACE="${POLARIS_WIFI_IFACE:-wlp8s0}"
OUT="${1:-/tmp/app-crash-watch.log}"
INTERVAL="${WATCH_INTERVAL:-5}"
MAX_POLLS="${WATCH_MAX_POLLS:-0}"
REPLAY="${WATCH_REPLAY:-0}"
case "$INTERVAL:$MAX_POLLS" in *[!0-9:]*) echo "WATCH_INTERVAL/WATCH_MAX_POLLS must be integers" >&2; exit 2 ;; esac
case "$REPLAY" in 0|1) ;; *) echo "WATCH_REPLAY must be 0 or 1" >&2; exit 2 ;; esac

ts() { date -u +%FT%TZ; }
log() { echo "$(ts) $*" >> "$OUT"; }

verify_identity() {
    local link bssid ssid route_dev fw
    link=$(iw dev "$WIFI_IFACE" link 2>/dev/null) || link=""
    bssid=$(printf '%s\n' "$link" | awk 'tolower($1)=="connected" && tolower($2)=="to" {print tolower($3); exit}')
    ssid=$(printf '%s\n' "$link" | awk -F': ' '/^[[:space:]]*SSID:/ {print $2; exit}')
    case "$bssid" in
        48:e7:da:*) ;;
        *) echo "Refusing watcher: no verified Polaris BSSID on $WIFI_IFACE" >&2; return 1 ;;
    esac
    case "$ssid" in
        polaris_*) ;;
        *) echo "Refusing watcher: associated SSID is not polaris_*" >&2; return 1 ;;
    esac
    route_dev=$(ip route get "$GIMBAL_IP" 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')
    [ "$route_dev" = "$WIFI_IFACE" ] || {
        echo "Refusing watcher: route to $GIMBAL_IP uses '${route_dev:-none}', not $WIFI_IFACE" >&2
        return 1
    }
    fw=$(timeout 12 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" 'cat /app/FwVer' 2>/dev/null) || fw=""
    case "$fw" in
        FwVer:*) ;;
        *) echo "Refusing watcher: SSH identity check did not return /app/FwVer" >&2; return 1 ;;
    esac
    log "IDENTITY bssid=$bssid ssid=$ssid route_dev=$route_dev $fw"
}

camera_present() {
    timeout 12 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" \
        'lsusb | grep -icE "05a9|25fb"' 2>/dev/null | tail -1
}

snapshot_device() {
    local label="$1"
    log "--- device snapshot: $label ---"
    timeout 25 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" '
        echo "== device time / firmware =="
        date
        cat /app/FwVer
        echo "== USB cameras =="
        lsusb | grep -iE "05a9|25fb" || true
        echo "== TCP peers =="
        netstat -tan | grep 9090 || true
        echo "== current Mlog =="
        tail -n 200 /app/Mlog.txt 2>/dev/null || true
        echo "== current Clog =="
        tail -n 200 /app/Clog.txt 2>/dev/null || true
        echo "== newest persistent Mlog =="
        latest=$(ls -t /app/sd/system/log/Mlog_* 2>/dev/null | head -1)
        [ -z "$latest" ] || tail -n 500 "$latest"
        echo "== newest persistent Clog =="
        latest=$(ls -t /app/sd/system/log/Clog_* 2>/dev/null | head -1)
        [ -z "$latest" ] || tail -n 500 "$latest"
    ' >> "$OUT" 2>&1
}

if ! verify_identity; then
    exit 1
fi
log "=== watch start (host=$HOST interval=${INTERVAL}s replay=$REPLAY max_polls=$MAX_POLLS) ==="
prev="unknown"
polls=0
while :; do
    cur=$(camera_present)
    [ -z "$cur" ] && cur="?"
    polls=$((polls + 1))
    if [ "$cur" != "$prev" ]; then
        log "CAMERA_STATE change: $prev -> $cur"
        prev="$cur"
        if [ "$cur" = "1" ]; then
            snapshot_device "before diagnostic replay"
            if [ "$REPLAY" = "1" ]; then
                log "--- separate host app-burst replay (not native phone traffic) ---"
                timeout 90 python3 "$(dirname "$0")/app-burst.py" >> "$OUT" 2>&1
                snapshot_device "after diagnostic replay"
            fi
        fi
    fi
    if [ "$MAX_POLLS" -gt 0 ] && [ "$polls" -ge "$MAX_POLLS" ]; then
        log "watch stop: reached WATCH_MAX_POLLS=$MAX_POLLS"
        break
    fi
    sleep "$INTERVAL"
done
