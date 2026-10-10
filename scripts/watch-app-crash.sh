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
# The second trap is the one #187 kept walking past. Camera presence was the
# only poll, and a failed SSH was recorded as CAMERA_STATE "?", so seven
# transport losses in one evening (docs/evidence/benro-connect-crash-20261008/
# raw/app-crash-watch-20261009-authorized-attempt.txt) were logged as camera
# observations. The operator-visible symptom is "the Polaris stops answering and
# then Benro Connect dies" - a link/device event, not a camera event. So the
# host-side identity is re-verified on EVERY poll and any failure is attributed
# instead of being folded into the camera reading:
#
#   LINK_LOSS_HOST      host is no longer associated to the polaris_* AP, or the
#                       route to 192.168.0.1 left the Wi-Fi interface. The route
#                       check matters: the home router shares 192.168.0.1, so a
#                       route off the Wi-Fi interface answers ping and proves
#                       nothing (issue #170).
#   DEVICE_SSH_DOWN     host side is correct and ICMP answers, but SSH does not
#                       - the refused/unreachable split already used by
#                       scripts/control-liveness.py.
#   DEVICE_UNREACHABLE  host side is correct but ICMP fails - the Polaris data
#                       path itself is gone (issue #171/#68 candidate).
#
# Camera presence is polled only while the link is OK, and any camera reading
# across a gap is treated as stale, so a transport loss can never again
# masquerade as a camera state. The dhd tdata_psh_info/tdata_disc_grp counters
# (#171) are sampled inside the window - on every recovery into OK and inside
# every device snapshot - not only from a separate camera-off run.
#
# No capture/shutter command is sent by this watcher. Output is one timestamped
# host-side file containing link-state transitions, camera USB transitions, and
# separately labeled pre-replay, optional replay, and post-replay evidence.
set -u
HOST="${POLARIS_SSH:-root@192.168.0.1}"
GIMBAL_IP="${POLARIS_IP:-192.168.0.1}"
WIFI_IFACE="${POLARIS_WIFI_IFACE:-wlp8s0}"
# AGENTS.md pins the Polaris OUI as data, not code: the interface above is
# env-overridable, so the BSSID prefix has to be too. The default is the same
# value the pinned BSSID 48:e7:da:d4:b5:73 starts with.
BSSID_PREFIX="${POLARIS_BSSID_PREFIX:-48:e7:da}"
# A default run must never clobber a previous one: /tmp/app-crash-watch.log
# currently holds a byte-identical copy of committed operator evidence.
OUT="${1:-/tmp/app-crash-watch-$(date -u +%Y%m%dT%H%M%SZ).log}"
INTERVAL="${WATCH_INTERVAL:-5}"
MAX_POLLS="${WATCH_MAX_POLLS:-0}"
REPLAY="${WATCH_REPLAY:-0}"
case "$INTERVAL:$MAX_POLLS" in *[!0-9:]*) echo "WATCH_INTERVAL/WATCH_MAX_POLLS must be integers" >&2; exit 2 ;; esac
case "$REPLAY" in 0|1) ;; *) echo "WATCH_REPLAY must be 0 or 1" >&2; exit 2 ;; esac

ts() { date -u +%FT%TZ; }
log() { echo "$(ts) $*" >> "$OUT"; }

# Host-side association/route check only - no device traffic. Sets
# LINK_FAIL_REASON so a lost run can still explain itself afterwards.
host_link_ok() {
    local link
    LINK_FAIL_REASON=""
    LINK_BSSID="" LINK_SSID="" LINK_ROUTE=""
    link=$(iw dev "$WIFI_IFACE" link 2>/dev/null) || link=""
    LINK_BSSID=$(printf '%s\n' "$link" | awk 'tolower($1)=="connected" && tolower($2)=="to" {print tolower($3); exit}')
    LINK_SSID=$(printf '%s\n' "$link" | awk -F': ' '/^[[:space:]]*SSID:/ {print $2; exit}')
    case "$LINK_BSSID" in
        "$BSSID_PREFIX":*) ;;
        *) LINK_FAIL_REASON="no verified Polaris BSSID on $WIFI_IFACE (bssid=${LINK_BSSID:-none})"; return 1 ;;
    esac
    case "$LINK_SSID" in
        polaris_*) ;;
        *) LINK_FAIL_REASON="associated SSID is not polaris_* (ssid=${LINK_SSID:-none})"; return 1 ;;
    esac
    LINK_ROUTE=$(ip route get "$GIMBAL_IP" 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')
    [ "$LINK_ROUTE" = "$WIFI_IFACE" ] || {
        LINK_FAIL_REASON="route to $GIMBAL_IP uses '${LINK_ROUTE:-none}', not $WIFI_IFACE"
        return 1
    }
    return 0
}

# Cheap device liveness probe - the same read-only identity query the watcher
# refuses to start without. Kept separate from camera_present so a device that
# is not answering is never issued a camera query.
probe_alive() {
    local fw
    fw=$(timeout 12 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" 'cat /app/FwVer' 2>/dev/null) || return 1
    printf '%s\n' "$fw" | grep -q '^FwVer:' || return 1
    printf '%s\n' "$fw"
}

# Non-TCP liveness: separates "data path gone" from "service not answering".
icmp_alive() {
    timeout 6 ping -c 1 -W 2 "$GIMBAL_IP" >/dev/null 2>&1
}

camera_present() {
    timeout 12 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" \
        'lsusb | grep -icE "05a9|25fb"' 2>/dev/null | tail -1
}

# Best-effort #171 driver counters; only obtainable while SSH works.
driver_counters() {
    local out
    out=$(timeout 12 ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" \
        'p=$(dmesg 2>/dev/null | grep -c "No more free tdata_psh_info" || true); d=$(dmesg 2>/dev/null | grep -c "Out of tdata_disc_grp" || true); echo "DRIVER_COUNTERS psh=$p disc=$d"' 2>/dev/null) || out=""
    [ -n "$out" ] && log "$out"
    return 0
}

verify_identity() {
    local fw
    host_link_ok || { echo "Refusing watcher: $LINK_FAIL_REASON" >&2; return 1; }
    fw=$(probe_alive) || { echo "Refusing watcher: SSH identity check did not return /app/FwVer" >&2; return 1; }
    log "IDENTITY bssid=$LINK_BSSID ssid=$LINK_SSID route_dev=$LINK_ROUTE $fw"
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
        echo "== dhd tdata counters (#171) =="
        echo "tdata_psh_info=$(dmesg 2>/dev/null | grep -c 'No more free tdata_psh_info' || true) tdata_disc_grp=$(dmesg 2>/dev/null | grep -c 'Out of tdata_disc_grp' || true)"
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
link_state="OK"
prev="unknown"
polls=0
while :; do
    polls=$((polls + 1))
    if ! host_link_ok; then
        cur_link="LINK_LOSS_HOST"
    elif probe_alive >/dev/null; then
        cur_link="OK"
    elif icmp_alive; then
        cur_link="DEVICE_SSH_DOWN"
    else
        cur_link="DEVICE_UNREACHABLE"
    fi
    if [ "$cur_link" != "$link_state" ]; then
        if [ "$cur_link" = "LINK_LOSS_HOST" ]; then
            log "LINK_STATE change: $link_state -> $cur_link reason=$LINK_FAIL_REASON"
        else
            log "LINK_STATE change: $link_state -> $cur_link"
        fi
        link_state="$cur_link"
        # A camera reading taken across a transport gap is stale by
        # construction, so force re-observation (and its snapshot) after
        # recovery rather than trusting the pre-gap value.
        prev="unknown"
        [ "$cur_link" = "OK" ] && driver_counters
    fi
    if [ "$link_state" = "OK" ]; then
        cur=$(camera_present)
        [ -z "$cur" ] && cur="?"
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
    fi
    if [ "$MAX_POLLS" -gt 0 ] && [ "$polls" -ge "$MAX_POLLS" ]; then
        log "watch stop: reached WATCH_MAX_POLLS=$MAX_POLLS"
        break
    fi
    sleep "$INTERVAL"
done
