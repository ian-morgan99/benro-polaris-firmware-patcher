#!/bin/sh
# ============================================================================
# polaris-frame-watch.sh -- solve completed JPEGs during an Astro session.
#
# This is deliberately a separate, opt-in daemon.  It only considers files
# while the head reports mode:8, waits for a stable JPEG, and records every
# decision.  It never fires the shutter and never touches a camera-side file.
# That boundary is what keeps ordinary K-3 III capture behaviour unchanged.
#
# The first implementation measures drift against the current target and can
# optionally re-centre with the already-qualified bounded GOTO path.  It does
# not pretend that image rotation can be corrected: that needs the independent
# axis-rate work in issue #240 and remains disabled until that firmware path is
# proven.
# ============================================================================
set -u

ASTRO=${ASTRO:-/app/astro}
LOG=${LOG:-/app/sd/polaris-astro/frame-watch.log}
HISTORY=${HISTORY:-/app/sd/polaris-astro/solve-history.jsonl}
STATE=${STATE:-/app/sd/polaris-astro/solved-jpegs.tsv}
TARGET_FILE=${TARGET_FILE:-/app/sd/polaris-astro/target.json}
FRAME_STATE=${FRAME_STATE:-/app/sd/polaris-astro/last-frame-solution.json}
MODE_FILE=${MODE_FILE:-/tmp/polaris-mode}
SOLVER_BIN=${SOLVER_BIN:-polaris-solve}
INDEPENDENT_CATALOG=${INDEPENDENT_CATALOG:-/app/sd/polaris-astro/catalogue.polcat}
FOCAL=${FOCAL_MM:-}
SENSOR_MM=${SENSOR_MM:-}
POLL=${FRAME_WATCH_POLL:-2}
STABLE_WAIT=${FRAME_STABLE_WAIT:-2}
MIN_BYTES=${FRAME_MIN_BYTES:-10000}
DRIFT_THRESH_DEG=${FRAME_DRIFT_THRESH_DEG:-0.02}
ROTATION_THRESH_DEG=${FRAME_ROTATION_THRESH_DEG:-1.0}
HINT_RADIUS=${FRAME_HINT_RADIUS:-15}
FALLBACK_RADIUS=${FRAME_FALLBACK_RADIUS:-60}
FRAME_CORRECT=${FRAME_CORRECT:-0}
MAX_CORRECTION_DEG=${FRAME_MAX_CORRECTION_DEG:-2.0}
MOUNT_HOST=${MOUNT_HOST:-127.0.0.1}
MOUNT_PORT=${MOUNT_PORT:-9090}
LAT=${LAT:-}
LON=${LON:-}

DIRS=${CAPTURE_DIR:-"/app/sd/normal /app/sd/starskyStack /app/sd/HDR /app/sd/panorama /app/sd/focusStack /app/sd/sun"}
EXTRA=${CAPTURE_GLOB_EXTRA:-"/app/sd/Lapse/class_*"}

mkdir -p "$(dirname "$LOG")" "$(dirname "$HISTORY")" "$(dirname "$FRAME_STATE")" 2>/dev/null

log() {
    _m="$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "$_m" >> "$LOG" 2>/dev/null
    echo "$_m" >&2
}

astro_active() {
    [ "$(cat "$MODE_FILE" 2>/dev/null)" = "8" ]
}

file_key() {
    _s=$(wc -c < "$1" 2>/dev/null | tr -d ' ')
    _t=$(stat -c %Y "$1" 2>/dev/null || echo 0)
    printf '%s\t%s\t%s\n' "$1" "${_s:-0}" "$_t"
}

seen() {
    [ -r "$STATE" ] && grep -F -q "$1	" "$STATE" 2>/dev/null
}

valid_stable_jpeg() {
    _f=$1
    _a=$(wc -c < "$_f" 2>/dev/null | tr -d ' ')
    [ "${_a:-0}" -ge "$MIN_BYTES" ] || return 1
    sleep "$STABLE_WAIT"
    _b=$(wc -c < "$_f" 2>/dev/null | tr -d ' ')
    [ "${_a:-0}" = "${_b:-1}" ] || return 1
    _tail=$(tail -c 2 "$_f" 2>/dev/null | od -An -t x1 | tr -d ' \n')
    [ "$_tail" = "ffd9" ]
}

target_from_file() {
    _tf=$1
    [ -r "$_tf" ] || return 1
    _ra=$(sed -n 's/.*"target_ra_deg":\([-0-9.]*\).*/\1/p' "$_tf" | head -1)
    _dec=$(sed -n 's/.*"target_dec_deg":\([-0-9.]*\).*/\1/p' "$_tf" | head -1)
    [ -n "$_ra" ] || _ra=$(sed -n 's/.*"ra_deg":\([-0-9.]*\).*/\1/p' "$_tf" | head -1)
    [ -n "$_dec" ] || _dec=$(sed -n 's/.*"dec_deg":\([-0-9.]*\).*/\1/p' "$_tf" | head -1)
    [ -n "$_ra" ] && [ -n "$_dec" ] || return 1
    printf '%s %s\n' "$_ra" "$_dec"
}

angular_sep_deg() {
    awk -v r1="$1" -v d1="$2" -v r2="$3" -v d2="$4" 'BEGIN {
        p=3.141592653589793/180; x=sin(d1*p)*sin(d2*p)+cos(d1*p)*cos(d2*p)*cos((r1-r2)*p);
        if (x>1) x=1; if (x<-1) x=-1;
        printf "%.6f", atan2(sqrt(1-x*x),x)/p
    }'
}

record_solution() {
    _json=$1
    _tmp="${FRAME_STATE}.tmp.$$"
    printf '%s\n' "$_json" > "$_tmp" 2>/dev/null && \
        mv "$_tmp" "$FRAME_STATE" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
    printf '%s\n' "$_json" > /tmp/polaris-last-frame-solution.json
}

solve_one() {
    _f=$1
    [ -x "$ASTRO/polaris-align.sh" ] || { log "missing polaris-align.sh"; return 1; }
    run_align() {
        _mount_hint=$1
        shift
        EMBED_SOLVE_EXIF=${EMBED_SOLVE_EXIF:-1} \
        SOLVER_BIN="$SOLVER_BIN" INDEPENDENT_CATALOG="$INDEPENDENT_CATALOG" \
        INDEPENDENT_CATALOG_DIR="${INDEPENDENT_CATALOG_DIR:-/app/sd/polaris-astro/catalogue-tiles}" \
        INDEPENDENT_CATALOG_MANIFEST="${INDEPENDENT_CATALOG_MANIFEST:-/app/sd/polaris-astro/catalogue-tiles.manifest.json}" \
        INDEPENDENT_TRIANGLE_INDEX="${INDEPENDENT_TRIANGLE_INDEX:-/app/sd/polaris-astro/catalogue-tiles.ptri}" \
        INDEPENDENT_MAX_CATALOG="${INDEPENDENT_MAX_CATALOG:-60}" \
        INDEPENDENT_SCALE_TOL="${INDEPENDENT_SCALE_TOL:-0.15}" \
        SENSOR_MM="$SENSOR_MM" MOUNT_HINT="$_mount_hint" FOCAL_MM="$FOCAL" \
        HINT_RADIUS="$HINT_RADIUS" \
            sh "$ASTRO/polaris-align.sh" "$_f" "$FOCAL" "$@" 2>>"$LOG"
    }
    _target=$(target_from_file "$TARGET_FILE" 2>/dev/null || \
              target_from_file /tmp/polaris-last-solution.json 2>/dev/null || true)
    if [ -n "$_target" ]; then
        _tra=$(echo "$_target" | awk '{print $1}'); _tdec=$(echo "$_target" | awk '{print $2}')
        log "solving $(basename "$_f") with target hint ra=$_tra dec=$_tdec radius=${HINT_RADIUS}deg"
        _out=$(run_align 1 "$_tra" "$_tdec" "$HINT_RADIUS")
    else
        _out=$(run_align 1)
    fi
    if ! printf '%s' "$_out" | grep -q '"solved":true' && [ -n "$_target" ] && [ "$FALLBACK_RADIUS" != "$HINT_RADIUS" ]; then
        log "hinted frame solve failed; retrying target radius=${FALLBACK_RADIUS}deg"
        _out=$(run_align 0 "$_tra" "$_tdec" "$FALLBACK_RADIUS")
    fi
    printf '%s\n' "$_out" | tail -1
}

quality_ok() {
    _j=$1
    printf '%s' "$_j" | grep -q '"solved":true' || return 1
    if [ "$SOLVER_BIN" != "polaris-solve" ]; then
        _n=$(printf '%s' "$_j" | sed -n 's/.*"matched_count":\([0-9]*\).*/\1/p')
        _r=$(printf '%s' "$_j" | sed -n 's/.*"rms_px":\([-0-9.]*\).*/\1/p')
        [ "${_n:-0}" -ge "${MIN_MATCHES:-12}" ] 2>/dev/null || return 1
        [ -n "$_r" ] || return 1
        awk -v r="$_r" -v m="${MAX_SOLVE_RMS_PX:-3.0}" 'BEGIN { exit !(r <= m) }'
        return $?
    fi
    _n=$(printf '%s' "$_j" | sed -n 's/.*"nmatch":\([0-9]*\).*/\1/p')
    _l=$(printf '%s' "$_j" | sed -n 's/.*"logodds":\([0-9.]*\).*/\1/p')
    [ "${_n:-0}" -ge "${MIN_MATCHES:-12}" ] 2>/dev/null || return 1
    [ "${_l%%.*:-0}" -ge "${MIN_LOGODDS:-100}" ] 2>/dev/null
}

assess_and_optionally_correct() {
    _f=$1; _j=$2
    _ra=$(printf '%s' "$_j" | sed -n 's/.*"ra_deg":\([-0-9.]*\).*/\1/p')
    _dec=$(printf '%s' "$_j" | sed -n 's/.*"dec_deg":\([-0-9.]*\).*/\1/p')
    _rot=$(printf '%s' "$_j" | sed -n 's/.*"rotation_deg":\([-0-9.]*\).*/\1/p')
    [ -n "$_ra" ] && [ -n "$_dec" ] || return 0
    _rotation_bad=0
    if [ -n "$_rot" ] && awk -v r="$_rot" -v t="$ROTATION_THRESH_DEG" 'BEGIN { exit !(sqrt(r*r) > t) }'; then
        _rotation_bad=1
        log "field rotation exceeds ${ROTATION_THRESH_DEG}deg; no axis-rate command is sent"
    fi

    _target=$(target_from_file "$TARGET_FILE" 2>/dev/null || \
              target_from_file /tmp/polaris-last-solution.json 2>/dev/null || true)
    if [ -n "$_target" ]; then
        _tra=$(echo "$_target" | awk '{print $1}'); _tdec=$(echo "$_target" | awk '{print $2}')
        _drift=$(angular_sep_deg "$_ra" "$_dec" "$_tra" "$_tdec")
        log "frame=$(basename "$_f") solved_ra=$_ra solved_dec=$_dec target_ra=$_tra target_dec=$_tdec drift_deg=$_drift rotation_deg=${_rot:-unknown}"
        _over=$(awk -v d="$_drift" -v t="$DRIFT_THRESH_DEG" 'BEGIN { print (d > t) ? 1 : 0 }')
        if [ "$_over" = "1" ]; then
            _too_big=$(awk -v d="$_drift" -v m="$MAX_CORRECTION_DEG" 'BEGIN { print (d > m) ? 1 : 0 }')
            if [ "$_too_big" = "1" ]; then
                log "refusing frame correction: drift ${_drift}deg exceeds ${MAX_CORRECTION_DEG}deg"
            elif [ "$_rotation_bad" = "1" ]; then
                log "withholding frame correction while field rotation is above threshold"
            elif [ "$FRAME_CORRECT" = "1" ] && [ -n "$LAT" ] && [ -n "$LON" ]; then
                log "correcting frame drift with bounded goto-radec to target"
                "$ASTRO/polaris-mount" --host "$MOUNT_HOST" --port "$MOUNT_PORT" \
                    --lat "$LAT" --lon "$LON" goto-radec --ra "$_tra" --dec "$_tdec" \
                    --refine-arcmin 0.1 >>"$LOG" 2>&1 || log "frame correction command failed"
            else
                log "frame drift exceeds threshold; correction disabled (FRAME_CORRECT=$FRAME_CORRECT)"
            fi
        fi
    else
        log "frame=$(basename "$_f") solved_ra=$_ra solved_dec=$_dec (no target anchor)"
    fi
}

process() {
    _f=$1
    seen "$_f" && return 0
    valid_stable_jpeg "$_f" || return 0
    _key=$(file_key "$_f")
    printf '%s' "$_key" >> "$STATE" 2>/dev/null
    log "processing completed Astro JPEG $_f"
    _j=$(solve_one "$_f")
    printf '%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$_j" >> "$HISTORY" 2>/dev/null
    if quality_ok "$_j"; then
        record_solution "$_j"
        assess_and_optionally_correct "$_f" "$_j"
    else
        log "solve rejected for $(basename "$_f"): $_j"
    fi
}

log "frame watcher started (mode-gated; correction=$FRAME_CORRECT solver=$SOLVER_BIN)"
while :; do
    if astro_active; then
        for _d in $DIRS $EXTRA; do
            [ -d "$_d" ] || continue
            for _f in "$_d"/*.jpg "$_d"/*.JPG; do
                [ -f "$_f" ] || continue
                process "$_f"
            done
        done
    fi
    sleep "$POLL"
done
