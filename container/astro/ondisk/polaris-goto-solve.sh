#!/bin/sh
# ============================================================================
# polaris-goto-solve.sh -- GOTO followed by a live-view plate solve.
#
# It is the common operation behind the Polaris web UI and the optional
# BenroConnect 519 watcher. The caller supplies the intended J2000 RA/Dec;
# the image is then solved against that hint. A successful solve becomes the
# next durable target record, so repeated GOTOs can refine the heading.
#
# Motion and heading correction are separately gated:
#   --already-there       do not issue a GOTO; solve after an app GOTO
#   GOTO_SOLVE_APPLY=1    permit a high-confidence 527 correction
#   GOTO_SOLVE_RECENTER=1 reissue the target GOTO after that correction
# Defaults are dry/non-mutating for the correction step. A failed solve never
# sends a mount command.
# ============================================================================
set -u

ASTRO=${ASTRO:-/app/astro}
LOG=${LOG:-/app/sd/polaris-astro/goto-solve.log}
HISTORY=${HISTORY:-/app/sd/polaris-astro/goto-history.jsonl}
TARGET_FILE=${TARGET_FILE:-/app/sd/polaris-astro/target.json}
SOLVER_BIN=${SOLVER_BIN:-polaris-solve}
INDEPENDENT_CATALOG=${INDEPENDENT_CATALOG:-/app/sd/polaris-astro/catalogue.polcat}
FOCAL=${FOCAL_MM:-}
SENSOR_MM=${SENSOR_MM:-}
LAT=${LAT:-}
LON=${LON:-}
MOUNT_HOST=${MOUNT_HOST:-127.0.0.1}
MOUNT_PORT=${MOUNT_PORT:-9090}
LIVEVIEW_HOST=${LIVEVIEW_HOST:-127.0.0.1}
LIVEVIEW_PORT=${LIVEVIEW_PORT:-8080}
HINT_RADIUS=${GOTO_HINT_RADIUS:-15}
FALLBACK_RADIUS=${GOTO_FALLBACK_RADIUS:-60}
SETTLE=${GOTO_SETTLE:-6}
APPLY=${GOTO_SOLVE_APPLY:-0}
RECENTER=${GOTO_SOLVE_RECENTER:-1}
FRAME=""
ALREADY=0
RA=""; DEC=""

mkdir -p "$(dirname "$LOG")" "$(dirname "$HISTORY")" 2>/dev/null
log() { _m="$(date '+%Y-%m-%d %H:%M:%S') $*"; echo "$_m" >> "$LOG" 2>/dev/null; echo "$_m" >&2; }

while [ $# -gt 0 ]; do
    case "$1" in
      --ra) RA="$2"; shift 2;;
      --dec) DEC="$2"; shift 2;;
      --frame) FRAME="$2"; shift 2;;
      --already-there) ALREADY=1; shift;;
      -h|--help) sed -n '2,22p' "$0"; exit 0;;
      *) echo "unknown argument: $1" >&2; exit 2;;
    esac
done

[ -n "$RA" ] && [ -n "$DEC" ] || { echo "--ra and --dec are required" >&2; exit 2; }
[ -n "$LAT" ] && [ -n "$LON" ] || { echo "LAT and LON are required" >&2; exit 2; }
[ -x "$ASTRO/polaris-align.sh" ] || { echo "missing polaris-align.sh" >&2; exit 2; }

if [ "$ALREADY" != "1" ]; then
    log "GOTO target ra=$RA dec=$DEC"
    "$ASTRO/polaris-mount" --host "$MOUNT_HOST" --port "$MOUNT_PORT" \
        --lat "$LAT" --lon "$LON" goto-radec --ra "$RA" --dec "$DEC" \
        --refine-arcmin 0.1 >>"$LOG" 2>&1 || { log "GOTO failed; no solve"; exit 1; }
fi

if [ -z "$FRAME" ]; then
    FRAME="/tmp/polaris-goto-solve.$$.jpg"
    trap 'rm -f "$FRAME" 2>/dev/null' EXIT
    sleep "$SETTLE"
    "$ASTRO/polaris-mount" --host "$LIVEVIEW_HOST" --port "$LIVEVIEW_PORT" \
        fetch --url-path "/?action=snapshot" --out "$FRAME" >/dev/null 2>&1 || {
        log "live-view snapshot failed"; exit 1;
    }
    [ -s "$FRAME" ] || { log "live-view snapshot was empty"; exit 1; }
fi

solve() {
    _radius=$1
    EMBED_SOLVE_EXIF=0 SOLVER_BIN="$SOLVER_BIN" \
    INDEPENDENT_CATALOG="$INDEPENDENT_CATALOG" SENSOR_MM="$SENSOR_MM" \
    INDEPENDENT_CATALOG_DIR="${INDEPENDENT_CATALOG_DIR:-/app/sd/polaris-astro/catalogue-tiles}" \
    INDEPENDENT_CATALOG_MANIFEST="${INDEPENDENT_CATALOG_MANIFEST:-/app/sd/polaris-astro/catalogue-tiles.manifest.json}" \
    INDEPENDENT_MAX_CATALOG="${INDEPENDENT_MAX_CATALOG:-60}" \
    INDEPENDENT_SCALE_TOL="${INDEPENDENT_SCALE_TOL:-0.15}" \
    MOUNT_HINT=0 FOCAL_MM="$FOCAL" \
        sh "$ASTRO/polaris-align.sh" "$FRAME" "$FOCAL" "$RA" "$DEC" "$_radius" 2>>"$LOG"
}

J=$(solve "$HINT_RADIUS" | tail -1)
if ! echo "$J" | grep -q '"solved":true'; then
    log "hinted solve failed at ${HINT_RADIUS}deg; retrying at ${FALLBACK_RADIUS}deg"
    J=$(solve "$FALLBACK_RADIUS" | tail -1)
fi
printf '%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$J" >> "$HISTORY" 2>/dev/null

quality_ok() {
    echo "$1" | grep -q '"solved":true' || return 1
    if [ "$SOLVER_BIN" != "polaris-solve" ]; then
        _n=$(echo "$1" | sed -n 's/.*"matched_count":\([0-9]*\).*/\1/p')
        _r=$(echo "$1" | sed -n 's/.*"rms_px":\([-0-9.]*\).*/\1/p')
        [ "${_n:-0}" -ge "${MIN_MATCHES:-12}" ] 2>/dev/null || return 1
        [ -n "$_r" ] || return 1
        awk -v r="$_r" -v m="${MAX_SOLVE_RMS_PX:-3.0}" 'BEGIN { exit !(r <= m) }'
        return $?
    fi
    _n=$(echo "$1" | sed -n 's/.*"nmatch":\([0-9]*\).*/\1/p')
    _l=$(echo "$1" | sed -n 's/.*"logodds":\([0-9.]*\).*/\1/p')
    [ "${_n:-0}" -ge "${MIN_MATCHES:-12}" ] 2>/dev/null || return 1
    [ "${_l%%.*:-0}" -ge "${MIN_LOGODDS:-100}" ] 2>/dev/null
}

if ! quality_ok "$J"; then
    log "GOTO solve rejected: $J"
    echo "$J"
    exit 1
fi

SRA=$(echo "$J" | sed -n 's/.*"ra_deg":\([-0-9.]*\).*/\1/p')
SDEC=$(echo "$J" | sed -n 's/.*"dec_deg":\([-0-9.]*\).*/\1/p')
SROT=$(echo "$J" | sed -n 's/.*"rotation_deg":\([-0-9.]*\).*/\1/p')
[ -n "$SRA" ] && [ -n "$SDEC" ] || { log "accepted solve has no usable RA/Dec"; echo "$J"; exit 1; }
mkdir -p "$(dirname "$TARGET_FILE")" 2>/dev/null
_target_tmp="${TARGET_FILE}.tmp.$$"
printf '{"target_ra_deg":%s,"target_dec_deg":%s,"solved_ra_deg":%s,"solved_dec_deg":%s,"rotation_deg":%s,"updated":"%s"}\n' \
    "$RA" "$DEC" "$SRA" "$SDEC" "${SROT:-0}" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$_target_tmp" 2>/dev/null \
    && mv "$_target_tmp" "$TARGET_FILE" 2>/dev/null || { rm -f "$_target_tmp" 2>/dev/null; log "could not publish target record"; exit 1; }

if [ "$APPLY" = "1" ]; then
    log "applying high-confidence solve to compass heading (527)"
    "$ASTRO/polaris-mount" --host "$MOUNT_HOST" --port "$MOUNT_PORT" \
        --lat "$LAT" --lon "$LON" align --solved-ra "$SRA" --solved-dec "$SDEC" \
        >>"$LOG" 2>&1 || { log "heading correction failed"; echo "$J"; exit 1; }
    if [ "$RECENTER" = "1" ]; then
        log "recentring corrected target"
        "$ASTRO/polaris-mount" --host "$MOUNT_HOST" --port "$MOUNT_PORT" \
            --lat "$LAT" --lon "$LON" goto-radec --ra "$RA" --dec "$DEC" \
            --refine-arcmin 0.1 >>"$LOG" 2>&1 || log "recenter GOTO failed"
    fi
else
    log "solve accepted; heading correction disabled (GOTO_SOLVE_APPLY=$APPLY)"
fi

echo "$J"
