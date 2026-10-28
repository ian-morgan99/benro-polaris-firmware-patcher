#!/bin/sh
# ============================================================================
# polaris-goto-watch.sh -- recognise BenroConnect Astro GOTOs and solve them.
#
# BenroConnect remains the owner of the GOTO. We only react to an app 519 whose
# track field is 1 while mode 8 is active, convert its wire alt/az target to
# J2000 RA/Dec, and solve a post-slew live-view frame. Calibration 519 messages
# carry track:0 and are intentionally ignored here.
# ============================================================================
set -u

ASTRO=${ASTRO:-/app/astro}
LOG=${LOG:-/app/sd/polaris-astro/goto-watch.log}
MODE_FILE=${MODE_FILE:-/tmp/polaris-mode}
PENDING_DIR=${PENDING_DIR:-/tmp/polaris-goto.queue}
LOCK_DIR=${LOCK_DIR:-/tmp/polaris-goto-worker.lock}
LAT=${LAT:-}; LON=${LON:-}
TZ_OFFSET_SEC=${TZ_OFFSET_SEC:-0}

mkdir -p "$(dirname "$LOG")" 2>/dev/null
log() { _m="$(date '+%Y-%m-%d %H:%M:%S') $*"; echo "$_m" >> "$LOG" 2>/dev/null; echo "$_m" >&2; }

app_connected() {
    netstat -tn 2>/dev/null | grep ':9090' | grep -q 'ESTABLISHED' || return 1
}

wire_to_az() {
    awk -v y="$1" 'BEGIN { if (y >= 0) a=360-y; else a=-y;
        while (a<0)a+=360; while(a>=360)a-=360; printf "%.6f",a }'
}

worker() {
    while :; do
        _req=""
        for _candidate in "$PENDING_DIR"/req.*; do
            [ -f "$_candidate" ] || continue
            _req=$_candidate
            break
        done
        if [ -z "$_req" ]; then
            sleep 1
            _retry=""
            for _candidate in "$PENDING_DIR"/req.*; do
                [ -f "$_candidate" ] || continue
                _retry=$_candidate
                break
            done
            [ -n "$_retry" ] || break
            _req=$_retry
        fi
        _pair=$(cat "$_req" 2>/dev/null)
        rm -f "$_req" 2>/dev/null
        _ra=$(echo "$_pair" | awk '{print $1}'); _dec=$(echo "$_pair" | awk '{print $2}')
        [ -n "$_ra" ] && [ -n "$_dec" ] || continue
        log "solving BenroConnect GOTO target ra=$_ra dec=$_dec"
        LAT="$LAT" LON="$LON" TZ_OFFSET_SEC="$TZ_OFFSET_SEC" \
            sh "$ASTRO/polaris-goto-solve.sh" --ra "$_ra" --dec "$_dec" \
            --already-there >>"$LOG" 2>&1 || log "GOTO solve failed for ra=$_ra dec=$_dec"
    done
    rm -f "$LOCK_DIR/pid" 2>/dev/null
    rmdir "$LOCK_DIR" 2>/dev/null || true
}

enqueue() {
    mkdir -p "$PENDING_DIR" 2>/dev/null || return 1
    _tmp=$(mktemp "$PENDING_DIR/.new.XXXXXX" 2>/dev/null) || return 1
    printf '%s %s\n' "$1" "$2" > "$_tmp"
    _req="$PENDING_DIR/req.$(basename "$_tmp" | sed 's/^\.new\.//')"
    mv "$_tmp" "$_req" 2>/dev/null || return 1
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        worker </dev/null >/dev/null 2>&1 &
        echo "$!" > "$LOCK_DIR/pid"
    elif [ -r "$LOCK_DIR/pid" ] && ! kill -0 "$(cat "$LOCK_DIR/pid" 2>/dev/null)" 2>/dev/null; then
        rm -f "$LOCK_DIR/pid" 2>/dev/null
        rmdir "$LOCK_DIR" 2>/dev/null || true
    fi
}

to_target() {
    _yaw=$1; _pitch=$2
    _az=$(wire_to_az "$_yaw")
    _clock=""; [ -r /tmp/polaris-tzoffset ] && _clock=$(cat /tmp/polaris-tzoffset 2>/dev/null)
    case "$_clock" in ''|*[!0-9-]*) _clock=$TZ_OFFSET_SEC;; esac
    _j=$("$ASTRO/polaris-mount" --lat "$LAT" --lon "$LON" --clock-offset "$_clock" \
         altaz2radec --alt "$_pitch" --az "$_az" 2>/dev/null)
    _ra=$(echo "$_j" | sed -n 's/.*"ra_deg":\([-0-9.]*\).*/\1/p')
    _dec=$(echo "$_j" | sed -n 's/.*"dec_deg":\([-0-9.]*\).*/\1/p')
    [ -n "$_ra" ] && [ -n "$_dec" ] && printf '%s %s\n' "$_ra" "$_dec"
}

[ -n "$LAT" ] && [ -n "$LON" ] || { log "LAT/LON required; watcher stopped"; exit 2; }
[ -x "$ASTRO/polaris-logwatch" ] || { log "missing polaris-logwatch"; exit 2; }
[ -x "$ASTRO/polaris-goto-solve.sh" ] || { log "missing polaris-goto-solve.sh"; exit 2; }

log "BenroConnect GOTO watcher started (track:1 only; mode 8 only)"
"$ASTRO/polaris-logwatch" --match "code:519" | while read -r line; do
    [ "$(cat "$MODE_FILE" 2>/dev/null)" = "8" ] || continue
    echo "$line" | grep -q 'track:1' || continue
    app_connected || { log "ignoring stale 519 without an app connection"; continue; }
    _yaw=$(echo "$line" | sed -n 's/.*yaw:\([-0-9.]*\).*/\1/p')
    _pitch=$(echo "$line" | sed -n 's/.*pitch:\([-0-9.]*\).*/\1/p')
    [ -n "$_yaw" ] && [ -n "$_pitch" ] || continue
    _target=$(to_target "$_yaw" "$_pitch")
    [ -n "$_target" ] || { log "could not derive RA/Dec from 519 yaw=$_yaw pitch=$_pitch"; continue; }
    enqueue $(echo "$_target")
done
