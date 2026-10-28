#!/bin/sh
# ============================================================================
# polaris-frame-watch.sh -- solve completed JPEGs during an Astro session.
#
# This is deliberately a separate, opt-in daemon.  It only considers files
# while the head reports mode:8, waits for a stable JPEG, and records every
# decision.  It never fires the shutter and never touches a camera-side file.
# The admission ledger is primed before each Astro session, so old gallery
# files are not mistaken for new Astro captures.  A file is admitted only when
# its path/size/mtime key has not been seen before; a reused filename with a
# changed key is therefore eligible again.
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
TELEMETRY=${FRAME_TELEMETRY:-/app/sd/polaris-astro/frame-telemetry.jsonl}
ADMISSION=${ADMISSION:-/app/sd/polaris-astro/frame-admission.tsv}
SESSION_FILE=${SESSION_FILE:-/app/sd/polaris-astro/session-id}
CAPTURE_EVENT_LEDGER=${CAPTURE_EVENT_LEDGER:-/app/sd/polaris-astro/capture-events.tsv}
FAILED_DIR=${FRAME_FAILED_DIR:-/app/sd/polaris-astro/failed}
FRAME_LOCK_DIR=${FRAME_LOCK_DIR:-${STATE}.lock}
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
FRAME_REQUIRE_CAPTURE_EVENT=${FRAME_REQUIRE_CAPTURE_EVENT:-1}
MAX_LOG_BYTES=${FRAME_MAX_LOG_BYTES:-1048576}
MAX_HISTORY_BYTES=${FRAME_MAX_HISTORY_BYTES:-1048576}
MAX_TELEMETRY_BYTES=${FRAME_MAX_TELEMETRY_BYTES:-2097152}
MAX_CAPTURE_EVENT_BYTES=${FRAME_MAX_CAPTURE_EVENT_BYTES:-1048576}
MAX_FAILED_FRAMES=${FRAME_MAX_FAILED_FRAMES:-20}
MAX_SOLVE_ATTEMPTS=${FRAME_MAX_SOLVE_ATTEMPTS:-3}
FRAME_RETRY_DELAY=${FRAME_RETRY_DELAY:-15}
FRAME_SOLVE_LEASE=${FRAME_SOLVE_LEASE:-300}

SESSION_ID=
SESSION_START_EPOCH=0

DIRS=${CAPTURE_DIR:-"/app/sd/normal /app/sd/starskyStack /app/sd/HDR /app/sd/panorama /app/sd/focusStack /app/sd/sun"}
EXTRA=${CAPTURE_GLOB_EXTRA:-"/app/sd/Lapse/class_*"}

mkdir -p "$(dirname "$LOG")" "$(dirname "$HISTORY")" \
    "$(dirname "$FRAME_STATE")" "$(dirname "$TELEMETRY")" \
    "$(dirname "$STATE")" "$(dirname "$ADMISSION")" \
    "$(dirname "$SESSION_FILE")" "$(dirname "$CAPTURE_EVENT_LEDGER")" \
    "$FAILED_DIR" 2>/dev/null

# Only one watcher may own the admission ledger.  This is intentionally a
# mkdir lock rather than a PID check: mkdir is atomic on the SD filesystem and
# a second boot hook cannot race the first into solving the same frame twice.
if ! mkdir "$FRAME_LOCK_DIR" 2>/dev/null; then
    exit 0
fi
printf '%s\n' "$$" > "$FRAME_LOCK_DIR/pid" 2>/dev/null || true
cleanup_lock() {
    rm -f "$FRAME_LOCK_DIR/pid" 2>/dev/null || true
    rmdir "$FRAME_LOCK_DIR" 2>/dev/null || true
}
stop_watcher() { exit 143; }
trap cleanup_lock EXIT
trap stop_watcher INT TERM

trim_file() {
    _path=$1
    _limit=$2
    [ -f "$_path" ] || return 0
    [ "${_limit:-0}" -gt 0 ] 2>/dev/null || return 0
    _bytes=$(wc -c < "$_path" 2>/dev/null | tr -d ' ')
    [ "${_bytes:-0}" -gt "$_limit" ] 2>/dev/null || return 0
    _tmp="${_path}.trim.$$"
    # Drop a possibly partial first line.  This keeps JSONL/TSV files
    # parseable after bounding them; raw tail -c would leave a corrupt record.
    tail -c "$_limit" "$_path" 2>/dev/null | sed '1d' > "$_tmp" 2>/dev/null && \
        mv "$_tmp" "$_path" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
}

log() {
    _m="$(date '+%Y-%m-%d %H:%M:%S') $*"
    trim_file "$LOG" "$MAX_LOG_BYTES"
    echo "$_m" >> "$LOG" 2>/dev/null
    echo "$_m" >&2
}

astro_active() {
    [ "$(cat "$MODE_FILE" 2>/dev/null)" = "8" ]
}

file_key() {
    _s=$(stat -c '%s' "$1" 2>/dev/null || true)
    _t=$(stat -c '%Y' "$1" 2>/dev/null || true)
    _i=$(stat -c '%i' "$1" 2>/dev/null || true)
    [ -n "$_s" ] && [ -n "$_t" ] && [ -n "$_i" ] || return 1
    printf '%s\t%s\t%s\t%s\n' "$1" "$_s" "$_t" "$_i"
}

state_lookup() {
    _key=$1
    _path=$(printf '%s\n' "$_key" | awk -F '\t' '{print $1}')
    _bytes=$(printf '%s\n' "$_key" | awk -F '\t' '{print $2}')
    _mtime=$(printf '%s\n' "$_key" | awk -F '\t' '{print $3}')
    _inode=$(printf '%s\n' "$_key" | awk -F '\t' '{print $4}')
    [ -r "$STATE" ] || return 1
    awk -F '\t' -v p="$_path" -v b="$_bytes" -v m="$_mtime" -v i="$_inode" \
        '$1 == p && $2 == b && $3 == m && $4 == i { v=$5 "\t" $6 "\t" $7 "\t" $8; found=1 } END { if (found) print v; else exit 1 }' \
        "$STATE" 2>/dev/null
}

state_update() {
    _key=$1; _status=$2; _attempts=$3; _next=$4; _reason=${5:-}
    _path=$(printf '%s\n' "$_key" | awk -F '\t' '{print $1}')
    _bytes=$(printf '%s\n' "$_key" | awk -F '\t' '{print $2}')
    _mtime=$(printf '%s\n' "$_key" | awk -F '\t' '{print $3}')
    _inode=$(printf '%s\n' "$_key" | awk -F '\t' '{print $4}')
    _tmp="${STATE}.tmp.$$"
    if [ -r "$STATE" ]; then
        awk -F '\t' -v p="$_path" -v b="$_bytes" -v m="$_mtime" -v i="$_inode" \
            '$1 != p || $2 != b || $3 != m || $4 != i' "$STATE" > "$_tmp" 2>/dev/null || :
    else
        : > "$_tmp" 2>/dev/null || return 1
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$_path" "$_bytes" "$_mtime" "$_inode" "$_status" "$_attempts" "$_next" "$_reason" >> "$_tmp" 2>/dev/null || {
        rm -f "$_tmp" 2>/dev/null; return 1;
    }
    mv "$_tmp" "$STATE" 2>/dev/null || { rm -f "$_tmp" 2>/dev/null; return 1; }
}

state_ready() {
    _key=$1
    _row=$(state_lookup "$_key" 2>/dev/null || true)
    [ -n "$_row" ] || return 0
    _status=$(printf '%s' "$_row" | awk -F '\t' '{print $1}')
    _next=$(printf '%s' "$_row" | awk -F '\t' '{print $3}')
    case "$_status" in
        baseline|accepted|rejected) return 1 ;;
        retry|waiting_event|solving)
            [ "${_next:-0}" -le "$(date +%s)" ] 2>/dev/null
            return $? ;;
        *) return 0 ;;
    esac
}

# Record the files already present at the point at which the watcher starts or
# an Astro session begins.  This is an admission boundary, not a solve result:
# a later file, or a later write to a reused path, has a different key and is
# processed normally.  Rows are state records, not a permanent "seen" list:
# failed solves can retry and stale in-flight work can be reclaimed.
prime_existing() {
    for _d in $DIRS $EXTRA; do
        [ -d "$_d" ] || continue
        for _f in "$_d"/*.jpg "$_d"/*.JPG "$_d"/*.jpeg "$_d"/*.JPEG; do
            [ -f "$_f" ] || continue
            _key=$(file_key "$_f")
            _mtime=$(printf '%s\n' "$_key" | awk -F '\t' '{print $3}')
            if [ "$FRAME_REQUIRE_CAPTURE_EVENT" = "0" ] || [ "$SESSION_START_EPOCH" -eq 0 ] 2>/dev/null || [ "${_mtime:-0}" -lt "$SESSION_START_EPOCH" ] 2>/dev/null; then
                state_update "$_key" baseline 0 0 startup
            elif capture_event_matches "$_f"; then
                : # A completed event raced the admission scan; leave it eligible.
            else
                state_update "$_key" waiting_event 0 "$((SESSION_START_EPOCH + FRAME_RETRY_DELAY))" no_event
            fi
        done
    done
    : > "$ADMISSION" 2>/dev/null || true
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$ADMISSION" 2>/dev/null || true
}

valid_stable_jpeg() {
    _f=$1
    _a=$(wc -c < "$_f" 2>/dev/null | tr -d ' ')
    [ "${_a:-0}" -ge "$MIN_BYTES" ] || return 1
    sleep "$STABLE_WAIT"
    _b=$(wc -c < "$_f" 2>/dev/null | tr -d ' ')
    [ "${_a:-0}" = "${_b:-1}" ] || return 1
    _tail=$(tail -c 2 "$_f" 2>/dev/null | od -An -t x1 | tr -d ' \n')
    [ "$_tail" = "ffd9" ] || return 1
    # libjpeg is the structural validator.  A starless but structurally valid
    # frame returns 3 from polaris-extract and remains eligible for solving;
    # truncated/corrupt JPEGs return a different failure code.
    if [ -x "$ASTRO/polaris-extract" ]; then
        "$ASTRO/polaris-extract" --jpeg "$_f" --downsample 8 --max-stars 1 >/dev/null 2>/dev/null
        _rc=$?
        [ "$_rc" -eq 0 ] || [ "$_rc" -eq 3 ] || return 1
    fi
    return 0
}

snapshot_frame() {
    _src=$1
    valid_stable_jpeg "$_src" || return 1
    _before=$(file_key "$_src") || return 1
    _tmp=$(mktemp "${TMPDIR:-/tmp}/polaris-frame.XXXXXX.jpg" 2>/dev/null) || return 1
    if ! cp "$_src" "$_tmp" 2>/dev/null; then
        rm -f "$_tmp" 2>/dev/null; return 1
    fi
    _after=$(file_key "$_src" 2>/dev/null || true)
    if [ "$_before" != "$_after" ] || ! valid_stable_jpeg "$_tmp"; then
        rm -f "$_tmp" 2>/dev/null; return 1
    fi
    # The stat key catches normal publication races; cksum catches an unusual
    # same-size rewrite whose mtime has not advanced at the filesystem tick.
    _src_crc=$(cksum "$_src" 2>/dev/null | awk '{print $1 "\t" $2}')
    _tmp_crc=$(cksum "$_tmp" 2>/dev/null | awk '{print $1 "\t" $2}')
    if [ -z "$_src_crc" ] || [ "$_src_crc" != "$_tmp_crc" ]; then
        rm -f "$_tmp" 2>/dev/null; return 1
    fi
    printf '%s\n' "$_tmp"
}

preserve_failed() {
    _snapshot=$1; _source=$2; _json=$3; _attempt=$4
    [ -f "$_snapshot" ] || return 0
    mkdir -p "$FAILED_DIR" 2>/dev/null || return 0
    _stamp=$(date -u '+%Y%m%dT%H%M%SZ')
    _base=$(basename "$_source")
    _dest="$FAILED_DIR/${_stamp}.$$.$_attempt.$_base"
    cp "$_snapshot" "$_dest" 2>/dev/null || return 0
    printf '%s\n' "$_json" > "$_dest.json" 2>/dev/null || true
    _n=0
    for _old in $(ls -1t "$FAILED_DIR"/*.jpg "$FAILED_DIR"/*.JPG "$FAILED_DIR"/*.jpeg "$FAILED_DIR"/*.JPEG 2>/dev/null); do
        _n=$((_n + 1))
        [ "$_n" -le "$MAX_FAILED_FRAMES" ] || rm -f "$_old" "$_old.json" 2>/dev/null || true
    done
}

writeback_exif_after_quality() {
    _source=$1; _snapshot=$2; _json=$3; _original_key=$4
    [ "${EXIF_WRITEBACK:-0}" = "1" ] || return 0
    [ -x "$ASTRO/polaris-exif-solve" ] || { log "EXIF writeback requested but polaris-exif-solve is missing"; return 1; }
    _json_tmp="${_snapshot}.json.$$"
    _out="${_source}.polaris-exif.tmp.$$"
    printf '%s\n' "$_json" > "$_json_tmp" 2>/dev/null || return 1
    if ! "$ASTRO/polaris-exif-solve" --in "$_snapshot" --out "$_out" --json "$_json_tmp" >/dev/null 2>>"$LOG"; then
        rm -f "$_json_tmp" "$_out" 2>/dev/null; return 1
    fi
    rm -f "$_json_tmp" 2>/dev/null
    if ! valid_stable_jpeg "$_out" || [ "$(file_key "$_source" 2>/dev/null || true)" != "$_original_key" ]; then
        rm -f "$_out" 2>/dev/null
        log "EXIF writeback refused: source changed or output failed validation"
        return 1
    fi
    mv "$_out" "$_source" 2>/dev/null || { rm -f "$_out" 2>/dev/null; return 1; }
    log "EXIF solve metadata committed after quality gate for $(basename "$_source")"
    return 0
}

# In the safe default mode, a stable JPEG is not enough: the capture/publish
# owner must append `epoch<TAB>path<TAB>bytes<TAB>mtime` to this ledger. This
# prevents an unrelated file written during Astro mode from being credited as
# the result of a camera capture. Set FRAME_REQUIRE_CAPTURE_EVENT=0 only for a
# controlled local-admission experiment while the producer is being wired.
capture_event_matches() {
    _f=$1
    [ "$FRAME_REQUIRE_CAPTURE_EVENT" = "0" ] && return 0
    [ -r "$CAPTURE_EVENT_LEDGER" ] || return 1
    _key=$(file_key "$_f")
    _bytes=$(echo "$_key" | awk -F '\t' '{print $2}')
    _mtime=$(echo "$_key" | awk -F '\t' '{print $3}')
    awk -F '\t' -v start="$SESSION_START_EPOCH" -v path="$_f" \
        -v bytes="$_bytes" -v mtime="$_mtime" \
        '($1 >= start && $2 == path && $3 == bytes && $4 == mtime) { found=1 } END { exit !found }' \
        "$CAPTURE_EVENT_LEDGER" 2>/dev/null
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

# A target from a previous Astro session must never become a hint or drift
# anchor for the next one. GOTO writes the session id; the mtime check also
# protects older target formats which predate that field.
session_target_from_file() {
    _tf=$1
    [ -r "$_tf" ] || return 1
    [ "$SESSION_START_EPOCH" -gt 0 ] 2>/dev/null || return 1
    _mtime=$(stat -c %Y "$_tf" 2>/dev/null || echo 0)
    [ "${_mtime:-0}" -ge "$SESSION_START_EPOCH" ] 2>/dev/null || return 1
    _sid=$(sed -n 's/.*"session_id":"\([^"]*\)".*/\1/p' "$_tf" | head -1)
    [ -n "$_sid" ] && [ "$_sid" = "$SESSION_ID" ] || return 1
    target_from_file "$_tf"
}

target_rotation_from_file() {
    _tf=$1
    [ -r "$_tf" ] || return 1
    sed -n 's/.*"rotation_deg":\([-0-9.]*\).*/\1/p' "$_tf" | head -1
}

angular_sep_deg() {
    awk -v r1="$1" -v d1="$2" -v r2="$3" -v d2="$4" 'BEGIN {
        p=3.141592653589793/180; x=sin(d1*p)*sin(d2*p)+cos(d1*p)*cos(d2*p)*cos((r1-r2)*p);
        if (x>1) x=1; if (x<-1) x=-1;
        printf "%.6f", atan2(sqrt(1-x*x),x)/p
    }'
}

angular_delta_deg() {
    awk -v a="$1" -v b="$2" 'BEGIN {
        d=a-b; while (d > 180) d-=360; while (d < -180) d+=360;
        if (d < 0) d=-d; printf "%.6f", d
    }'
}

record_solution() {
    _json=$1
    _tmp="${FRAME_STATE}.tmp.$$"
    printf '%s\n' "$_json" > "$_tmp" 2>/dev/null && \
        mv "$_tmp" "$FRAME_STATE" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
    _tmp_last=/tmp/polaris-last-frame-solution.json.tmp.$$
    printf '%s\n' "$_json" > "$_tmp_last" 2>/dev/null && \
        mv "$_tmp_last" /tmp/polaris-last-frame-solution.json 2>/dev/null || \
        rm -f "$_tmp_last" 2>/dev/null
}

solve_one() {
    _f=$1
    [ -x "$ASTRO/polaris-align.sh" ] || { log "missing polaris-align.sh"; return 1; }
    run_align() {
        _mount_hint=$1
        shift
        # The watcher solves an immutable snapshot.  Metadata is committed only
        # after the quality gate below, so a weak/false solve cannot mutate the
        # user's JPEG.
        EMBED_SOLVE_EXIF=0 \
        SOLVER_BIN="$SOLVER_BIN" INDEPENDENT_CATALOG="$INDEPENDENT_CATALOG" \
        INDEPENDENT_CATALOG_DIR="${INDEPENDENT_CATALOG_DIR:-/app/sd/polaris-astro/catalogue-tiles}" \
        INDEPENDENT_CATALOG_MANIFEST="${INDEPENDENT_CATALOG_MANIFEST:-/app/sd/polaris-astro/catalogue-tiles.manifest.json}" \
        INDEPENDENT_TRIANGLE_INDEX="${INDEPENDENT_TRIANGLE_INDEX:-/app/sd/polaris-astro/catalogue-tiles.ptri}" \
        INDEPENDENT_MAX_CATALOG="${INDEPENDENT_MAX_CATALOG:-120}" \
        INDEPENDENT_ANCHOR_STARS="${INDEPENDENT_ANCHOR_STARS:-10}" \
        INDEPENDENT_SCALE_TOL="${INDEPENDENT_SCALE_TOL:-0.15}" \
        INDEPENDENT_ATTEMPTS="${INDEPENDENT_ATTEMPTS:-40}" \
        SENSOR_MM="$SENSOR_MM" MOUNT_HINT="$_mount_hint" FOCAL_MM="$FOCAL" \
        HINT_RADIUS="$HINT_RADIUS" \
            sh "$ASTRO/polaris-align.sh" "$_f" "$FOCAL" "$@" 2>>"$LOG"
    }
    _target=$(session_target_from_file "$TARGET_FILE" 2>/dev/null || true)
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
    _frame_name=$(basename "$_f")
    _ra=$(printf '%s' "$_j" | sed -n 's/.*"ra_deg":\([-0-9.]*\).*/\1/p')
    _dec=$(printf '%s' "$_j" | sed -n 's/.*"dec_deg":\([-0-9.]*\).*/\1/p')
    _rot=$(printf '%s' "$_j" | sed -n 's/.*"rotation_deg":\([-0-9.]*\).*/\1/p')
    if [ -z "$_ra" ] || [ -z "$_dec" ]; then
        trim_file "$TELEMETRY" "$MAX_TELEMETRY_BYTES"
        printf '{"session_id":"%s","frame":"%s","solved":true,"target_available":false,"action":"missing_pose","rate_control":"unavailable"}\n' \
            "$SESSION_ID" "$_frame_name" >> "$TELEMETRY" 2>/dev/null
        return 0
    fi
    _target=$(session_target_from_file "$TARGET_FILE" 2>/dev/null || true)
    _rotation_bad=0
    if [ -n "$_target" ]; then
        _tra=$(echo "$_target" | awk '{print $1}'); _tdec=$(echo "$_target" | awk '{print $2}')
        _trot=$(target_rotation_from_file "$TARGET_FILE" 2>/dev/null || true)
        _rotation_delta=""
        if [ -n "$_rot" ] && [ -n "$_trot" ]; then
            _rotation_delta=$(angular_delta_deg "$_rot" "$_trot")
            if awk -v r="$_rotation_delta" -v t="$ROTATION_THRESH_DEG" 'BEGIN { exit !(r > t) }'; then
                _rotation_bad=1
                log "field rotation delta ${_rotation_delta}deg exceeds ${ROTATION_THRESH_DEG}deg; no axis-rate command is sent"
            fi
        fi
        _drift=$(angular_sep_deg "$_ra" "$_dec" "$_tra" "$_tdec")
        _action=within_tolerance
        log "frame=$(basename "$_f") solved_ra=$_ra solved_dec=$_dec target_ra=$_tra target_dec=$_tdec drift_deg=$_drift rotation_deg=${_rot:-unknown} rotation_delta_deg=${_rotation_delta:-unknown}"
        _over=$(awk -v d="$_drift" -v t="$DRIFT_THRESH_DEG" 'BEGIN { print (d > t) ? 1 : 0 }')
        if [ "$_over" = "1" ]; then
            _too_big=$(awk -v d="$_drift" -v m="$MAX_CORRECTION_DEG" 'BEGIN { print (d > m) ? 1 : 0 }')
            if [ "$_too_big" = "1" ]; then
                _action=refused_excessive_drift
                log "refusing frame correction: drift ${_drift}deg exceeds ${MAX_CORRECTION_DEG}deg"
            elif [ "$_rotation_bad" = "1" ]; then
                _action=withheld_rotation
                log "withholding frame correction while field rotation is above threshold"
            elif [ "$FRAME_CORRECT" = "1" ] && [ -n "$LAT" ] && [ -n "$LON" ]; then
                _action=bounded_goto
                log "correcting frame drift with bounded goto-radec to target"
                "$ASTRO/polaris-mount" --host "$MOUNT_HOST" --port "$MOUNT_PORT" \
                    --lat "$LAT" --lon "$LON" goto-radec --ra "$_tra" --dec "$_tdec" \
                    --refine-arcmin 0.1 >>"$LOG" 2>&1 || log "frame correction command failed"
            else
                _action=correction_disabled
                log "frame drift exceeds threshold; correction disabled (FRAME_CORRECT=$FRAME_CORRECT)"
            fi
        fi
        trim_file "$TELEMETRY" "$MAX_TELEMETRY_BYTES"
        printf '{"session_id":"%s","frame":"%s","solved":true,"target_available":true,"solved_ra_deg":%s,"solved_dec_deg":%s,"target_ra_deg":%s,"target_dec_deg":%s,"drift_deg":%s,"rotation_deg":%s,"target_rotation_deg":%s,"rotation_delta_deg":%s,"action":"%s","rate_control":"unavailable"}\n' \
            "$SESSION_ID" "$_frame_name" "$_ra" "$_dec" "$_tra" "$_tdec" "$_drift" \
            "${_rot:-null}" "${_trot:-null}" "${_rotation_delta:-null}" "$_action" \
            >> "$TELEMETRY" 2>/dev/null
    else
        log "frame=$(basename "$_f") solved_ra=$_ra solved_dec=$_dec (no target anchor)"
        trim_file "$TELEMETRY" "$MAX_TELEMETRY_BYTES"
        printf '{"session_id":"%s","frame":"%s","solved":true,"target_available":false,"solved_ra_deg":%s,"solved_dec_deg":%s,"rotation_deg":%s,"action":"no_target","rate_control":"unavailable"}\n' \
            "$SESSION_ID" "$_frame_name" "$_ra" "$_dec" "${_rot:-null}" >> "$TELEMETRY" 2>/dev/null
    fi
}

process() {
    _f=$1
    _key=$(file_key "$_f")
    state_ready "$_key" || return 0
    valid_stable_jpeg "$_f" || return 0
    if ! capture_event_matches "$_f"; then
        log "withholding $(basename "$_f"): no matching capture-completion event"
        state_update "$_key" waiting_event 0 "$(( $(date +%s) + FRAME_RETRY_DELAY ))" no_event
        return 0
    fi
    _snapshot=$(snapshot_frame "$_f" 2>/dev/null || true)
    [ -n "$_snapshot" ] || return 0
    _row=$(state_lookup "$_key" 2>/dev/null || true)
    _attempt=$(printf '%s' "$_row" | awk -F '\t' '{print $2}')
    _attempt=${_attempt:-0}
    _attempt=$((_attempt + 1))
    state_update "$_key" solving "$_attempt" "$(( $(date +%s) + FRAME_SOLVE_LEASE ))" in_progress
    log "processing completed Astro JPEG $_f"
    _j=$(solve_one "$_snapshot" 2>/dev/null || true)
    [ -n "$_j" ] || _j='{"solved":false,"failure_reason":"solver_no_output"}'
    if quality_ok "$_j"; then
        state_update "$_key" accepted "$_attempt" 0 quality_ok
        record_solution "$_j"
        writeback_exif_after_quality "$_f" "$_snapshot" "$_j" "$_key" || true
        # The source may now have a new EXIF key.  Record the post-write key so
        # our own atomic replacement cannot look like a fresh capture.
        _post_key=$(file_key "$_f" 2>/dev/null || true)
        [ -n "$_post_key" ] && state_update "$_post_key" accepted "$_attempt" 0 quality_ok
        assess_and_optionally_correct "$_f" "$_j"
    else
        preserve_failed "$_snapshot" "$_f" "$_j" "$_attempt"
        if [ "$_attempt" -lt "$MAX_SOLVE_ATTEMPTS" ] 2>/dev/null; then
            state_update "$_key" retry "$_attempt" "$(( $(date +%s) + FRAME_RETRY_DELAY ))" quality_rejected
            log "solve rejected for $(basename "$_f"); retry $_attempt/$MAX_SOLVE_ATTEMPTS: $_j"
        else
            state_update "$_key" rejected "$_attempt" 0 quality_rejected
            log "solve rejected permanently for $(basename "$_f"): $_j"
        fi
    fi
    trim_file "$HISTORY" "$MAX_HISTORY_BYTES"
    printf '%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$_j" >> "$HISTORY" 2>/dev/null
    rm -f "$_snapshot" 2>/dev/null
}

start_session() {
    SESSION_ID="$(date -u '+%Y%m%dT%H%M%SZ')-$$"
    SESSION_START_EPOCH="$(date +%s)"
    # Rotate only at the session boundary, before normal capture processing.
    # Rotating a ledger while gp_file_save() is appending could otherwise lose
    # a just-published event between the read and atomic rename.
    trim_file "$CAPTURE_EVENT_LEDGER" "$MAX_CAPTURE_EVENT_BYTES"
    printf '%s\n' "$SESSION_ID" > "${SESSION_FILE}.tmp.$$" 2>/dev/null && \
        mv "${SESSION_FILE}.tmp.$$" "$SESSION_FILE" 2>/dev/null || \
        rm -f "${SESSION_FILE}.tmp.$$" 2>/dev/null
    # Admission is session-scoped. Old state must not make a reused filename
    # look solved in the new session, and it must not grow without bound.
    : > "$STATE" 2>/dev/null || true
    prime_existing
    log "Astro session started id=$SESSION_ID"
}

prime_existing
_was_active=0
log "frame watcher started (mode-gated; correction=$FRAME_CORRECT solver=$SOLVER_BIN)"
while :; do
    _active=0
    astro_active && _active=1
    if [ "$_active" = "1" ]; then
        if [ "$_was_active" != "1" ]; then
            # Files made while Astro was not active are not Astro frames. Mark
            # them before scanning the first active session.
            start_session
            log "Astro frame admission opened"
        fi
        for _d in $DIRS $EXTRA; do
            [ -d "$_d" ] || continue
            for _f in "$_d"/*.jpg "$_d"/*.JPG "$_d"/*.jpeg "$_d"/*.JPEG; do
                [ -f "$_f" ] || continue
                process "$_f"
            done
        done
    fi
    _was_active=$_active
    sleep "$POLL"
done
