#!/bin/sh
# ============================================================================
#  polaris-align.sh -- ONE frame in, one sky position out. Runs ON THE DEVICE.
#
#     polaris-align.sh <image.jpg> [focal_mm] [ra_hint dec_hint radius_deg]
#
#  Chains our two binaries: polaris-extract (JPEG -> star list) and
#  selected solver (star list -> RA/Dec/roll/scale). Prints the solver's JSON on
#  stdout and nothing else, so a caller can parse it.
#
#  Defaults assume the Polaris' own layout:
#     LAT / LON                 observer position; REQUIRED for the mount hint
#     ASTRO=/app/astro          binaries
#     INDEXES=/app/sd/astrometry   index files (on the microSD)
#     SENSOR_MM                 explicit sensor width in mm. If omitted, the
#                               JPEG's generic EXIF metadata and the optional
#                               SENSOR_PROFILE_FILE are consulted. An unknown
#                               camera uses a bounded generic fallback and is
#                               marked as assumed; set ALLOW_DEFAULT_SENSOR=0
#                               to fail closed instead.
#  Override any of them with environment variables.
#  SOLVER_BIN=polaris-solve-independent selects the alternate solver when it is
#  installed; the Astrometry.net solver remains the default.
#
#  A position hint is worth ~50x on a narrow field -- MEASURED ON THE DEVICE:
#  a 4.5 deg field (400mm on full frame) solves in 7.3 s with a 15 deg hint and
#  361.7 s without. So if no hint is passed we ASK THE MOUNT where it thinks it
#  is pointing and use that; the mount always knows roughly, even unaligned.
#  Pass MOUNT_HINT=0 to disable, or give ra/dec/radius explicitly.
# ============================================================================
ASTRO=${ASTRO:-/app/astro}
INDEXES=${INDEXES:-/app/sd/astrometry}
SOLVER_BIN=${SOLVER_BIN:-polaris-solve}
CAMERA_MODEL=${CAMERA_MODEL:-}
SENSOR_MM=${SENSOR_MM:-}
SENSOR_PROFILE_FILE=${SENSOR_PROFILE_FILE:-/app/sd/polaris-astro/camera-sensors.tsv}
SENSOR_DEFAULT_MM=${SENSOR_DEFAULT_MM:-36}
SENSOR_MIN_MM=${SENSOR_MIN_MM:-10}
SENSOR_MAX_MM=${SENSOR_MAX_MM:-54}
ALLOW_DEFAULT_SENSOR=${ALLOW_DEFAULT_SENSOR:-1}
INDEPENDENT_SCALE_TOL_ASSUMED=${INDEPENDENT_SCALE_TOL_ASSUMED:-0.60}
INDEPENDENT_CATALOG=${INDEPENDENT_CATALOG:-/app/sd/polaris-astro/catalogue.polcat}
INDEPENDENT_CATALOG_DIR=${INDEPENDENT_CATALOG_DIR:-/app/sd/polaris-astro/catalogue-tiles}
INDEPENDENT_CATALOG_MANIFEST=${INDEPENDENT_CATALOG_MANIFEST:-/app/sd/polaris-astro/catalogue-tiles.manifest.json}
INDEPENDENT_TRIANGLE_INDEX=${INDEPENDENT_TRIANGLE_INDEX:-/app/sd/polaris-astro/catalogue-tiles.ptri}
INDEPENDENT_MAX_CATALOG=${INDEPENDENT_MAX_CATALOG:-120}
INDEPENDENT_ANCHOR_STARS=${INDEPENDENT_ANCHOR_STARS:-10}
INDEPENDENT_SCALE_TOL=${INDEPENDENT_SCALE_TOL:-0.15}
INDEPENDENT_ATTEMPTS=${INDEPENDENT_ATTEMPTS:-40}
# Each independent child and the whole indexed search are bounded. A failed
# mount hint must never fall into an unbounded all-sky scan during capture.
INDEPENDENT_SOLVER_TIMEOUT=${INDEPENDENT_SOLVER_TIMEOUT:-10}
INDEPENDENT_SEARCH_TIMEOUT=${INDEPENDENT_SEARCH_TIMEOUT:-45}
INDEPENDENT_BLIND_FALLBACK=${INDEPENDENT_BLIND_FALLBACK:-0}
DOWNSAMPLE=${DOWNSAMPLE:-4}
MAXSTARS=${MAXSTARS:-200}
# never let one frame block the loop; a mismatched hint can grind for minutes
SOLVE_TIMEOUT=${SOLVE_TIMEOUT:-45}

IMG="$1"
FOCAL="${2:-}"
RA="${3:-}"; DEC="${4:-}"; RADIUS="${5:-}"
# The WebUI uses the explicit word auto for an optional focal input. Treat it
# as absent so EXIF/profile/cache inference remains the normal path.
[ "$FOCAL" = "auto" ] && FOCAL=""
USE_HINT=1

[ -n "$IMG" ] || { echo "usage: $0 <image.jpg> [focal_mm] [ra dec radius]" >&2; exit 2; }
[ -f "$IMG" ] || { echo "no such image: $IMG" >&2; exit 2; }
[ -x "$ASTRO/polaris-extract" ] || { echo "missing $ASTRO/polaris-extract" >&2; exit 2; }
[ -x "$ASTRO/$SOLVER_BIN" ] || { echo "missing solver $ASTRO/$SOLVER_BIN (set SOLVER_BIN=polaris-solve or install the alternate solver)" >&2; exit 2; }

EMBED_SOLVE_EXIF=${EMBED_SOLVE_EXIF:-${EXIF_WRITEBACK:-0}}
embed_solve_exif() {
    _result=$1
    [ "$EMBED_SOLVE_EXIF" = "1" ] || return 0
    [ -x "$ASTRO/polaris-exif-solve" ] || { echo "[polaris-align] EXIF writer unavailable; leaving image unchanged" >&2; return 0; }
    _meta=$(mktemp /tmp/polaris-solve-meta.XXXXXX) || return 0
    # Keep the replacement in the source directory so rename is atomic, but
    # use a unique name so two explicitly launched solve jobs cannot clobber
    # one another's temporary output.
    _tmp=$(mktemp "${IMG}.polaris-exif.tmp.XXXXXX") || { rm -f "$_meta"; return 0; }
    printf '{"polaris_solve":%s,"focal_mm":%s,"sensor_width_mm":%s,"sensor_source":"%s"}\n' \
        "$_result" "${EXIF_FOCAL:-${FOCAL:-0}}" "$SENSOR_MM" "$SENSOR_SOURCE" > "$_meta"
    if "$ASTRO/polaris-exif-solve" --in "$IMG" --out "$_tmp" --json "$_meta" 2>/dev/null \
       && [ -s "$_tmp" ] \
       && [ "$(tail -c 2 "$_tmp" 2>/dev/null | od -An -t x1 | tr -d ' \n')" = "ffd9" ]; then
        if mv "$_tmp" "$IMG" 2>/dev/null; then
            echo "[polaris-align] embedded validated solve in EXIF: $IMG" >&2
        else
            rm -f "$_tmp" 2>/dev/null
            echo "[polaris-align] EXIF replacement failed; original image preserved" >&2
        fi
    else
        rm -f "$_tmp" 2>/dev/null
        echo "[polaris-align] EXIF embedding failed; original image preserved" >&2
    fi
    rm -f "$_meta" 2>/dev/null
}
emit_solution() { embed_solve_exif "$1"; echo "$1"; }

# ---- solve diagnostics ----------------------------------------------------
# Issue #321: a solve that times out leaves no trace of why. Mlog and Clog cover
# the camera stack (pgphoto, ptp2, stage2) and never see this script at all, so a
# timeout was indistinguishable from "too few stars", "wrong hint" or "would have
# finished given more time".
#
# stdout is NOT touched. polaris-align.sh's contract is that stdout carries the
# solver JSON and nothing else -- callers parse it -- so diagnostics go to stderr
# and to SOLVE_LOG. autosolve.sh already redirects our stderr into its own log,
# so this shows up there too without any caller change.
#
# Timing uses /proc/uptime, not date. busybox date has no %N on this device
# (verified: `date +%s.%N` prints the literal ".%N"), and date is wall-clock --
# the Polaris has no RTC and NTP can step the clock mid-solve, which would report
# a negative or absurd duration. /proc/uptime is monotonic and already sub-second.
SOLVE_LOG=${SOLVE_LOG:-/app/sd/polaris-astro/solve.log}
solve_now() { awk '{print $1}' /proc/uptime 2>/dev/null || echo 0; }
slog() {
    _m="$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "[polaris-align] $_m" >&2
    { mkdir -p "$(dirname "$SOLVE_LOG")" 2>/dev/null; echo "$_m" >> "$SOLVE_LOG"; } 2>/dev/null || true
}

# ---- derive a pointing hint from the mount if we were not given one --------
MOUNT_HINT=${MOUNT_HINT:-1}
MOUNT_HOST=${MOUNT_HOST:-127.0.0.1}
MOUNT_PORT=${MOUNT_PORT:-9090}
# 60, NOT 20. The hint comes from the mount's compass, and the compass error is
# the very thing being measured, so the radius has to cover it. Measured against
# a 37.5 deg error on a 960x640 frame:
#     20 deg -> FAILED after 120 s (burned the whole cpulimit)
#     45 deg -> solved in 1 s
#     90 deg -> solved in 3 s
#     blind  -> solved in 3 s
# A too-narrow hint is WORSE THAN NO HINT: it fails, and it fails slowly. This
# default stayed at 20 long after that was written down, so every solve-now.sh
# run was handicapped by it.
HINT_RADIUS=${HINT_RADIUS:-60}
if [ -z "$RA" ] && [ "$MOUNT_HINT" = "1" ] && [ -n "${LAT:-}" ] && [ -n "${LON:-}" ] \
   && [ -x "$ASTRO/polaris-mount" ]; then
    POSE=$("$ASTRO/polaris-mount" --host "$MOUNT_HOST" --port "$MOUNT_PORT" \
           --lat "$LAT" --lon "$LON" pose 2>/dev/null)
    RA=$(echo "$POSE" | sed -n 's/.*"ra_deg":\([-0-9.]*\).*/\1/p')
    DEC=$(echo "$POSE" | sed -n 's/.*"dec_deg":\([-0-9.]*\).*/\1/p')
    if [ -n "$RA" ] && [ -n "$DEC" ]; then
        RADIUS=$HINT_RADIUS
        echo "[polaris-align] hint from mount: ra=$RA dec=$DEC r=${RADIUS}deg" >&2
    else
        RA=""; DEC=""
        echo "[polaris-align] no pose from the mount; solving blind (slow at long focal lengths)" >&2
    fi
fi

IDXARGS=""
for f in "$INDEXES"/index-*.fits; do
    [ -f "$f" ] || continue
    IDXARGS="$IDXARGS --index $f"
done
if [ "$SOLVER_BIN" = "polaris-solve" ]; then
    [ -n "$IDXARGS" ] || { echo "no Astrometry.net index files in $INDEXES" >&2; exit 2; }
else
    if [ "$SOLVER_BIN" = "polaris-solve-independent-search" ]; then
        [ -d "$INDEPENDENT_CATALOG_DIR" ] || { echo "missing independent catalogue directory $INDEPENDENT_CATALOG_DIR" >&2; exit 2; }
        [ -f "$INDEPENDENT_CATALOG_MANIFEST" ] || { echo "missing independent tile manifest $INDEPENDENT_CATALOG_MANIFEST" >&2; exit 2; }
        [ -f "$INDEPENDENT_TRIANGLE_INDEX" ] || { echo "missing independent triangle index $INDEPENDENT_TRIANGLE_INDEX" >&2; exit 2; }
    else
        [ -n "${INDEPENDENT_CATALOG:-}" ] || { echo "independent solver requires INDEPENDENT_CATALOG" >&2; exit 2; }
        [ -f "$INDEPENDENT_CATALOG" ] || { echo "missing independent catalogue $INDEPENDENT_CATALOG" >&2; exit 2; }
    fi
fi

STARS=$(mktemp /tmp/polaris-stars.XXXXXX) || exit 1
trap 'rm -f "$STARS"' EXIT

"$ASTRO/polaris-extract" --jpeg "$IMG" --downsample "$DOWNSAMPLE" \
    --max-stars "$MAXSTARS" --stats > "$STARS" 2>&2 || {
    echo '{"solved":false,"error":"extract failed"}'; exit 3; }

# the extractor records the full-resolution size in a comment; reuse it so the
# scale hint is in full-res pixels even though we detected on a reduced image
W=$(sed -n 's/^# full resolution \([0-9]*\) x .*/\1/p' "$STARS")
H=$(sed -n 's/^# full resolution [0-9]* x \([0-9]*\)/\1/p' "$STARS")
[ -n "$W" ] && [ -n "$H" ] || { echo '{"solved":false,"error":"no image size"}'; exit 3; }

# How many stars the extractor actually found. Header lines start with '#', so the
# rest of the file is the star list. This is the single most useful number for #321:
# a solve that times out having been given 4 stars is an image-quality problem, while
# one given 200 stars is a search-space or CPU problem, and the two need opposite fixes.
#
# grep -vc prints "0" AND exits 1 when nothing matches, so appending "|| echo 0" would
# capture the literal two lines "0\n0" and emit stars=0 followed by a stray line. The
# count is always printed; only the exit status varies, so it is taken as-is and then
# validated to be a plain integer.
_star_count=$(grep -vc '^#' "$STARS" 2>/dev/null)
case "$_star_count" in ''|*[!0-9]*) _star_count=0 ;; esac

# Issue #341. DOWNSAMPLE is chosen for an ~6000 px camera frame, and the WebUI
# upload path passes no DOWNSAMPLE at all, so a phone-downscaled upload lands on
# 4 regardless of its real size. A 1920x1280 JPEG decoded at 1/4 is 480x320 and
# yields single-digit stars; a triangle solver cannot match that against an
# all-sky index, so it returns "search_exhausted" -- which reads like missing
# index files but is not. Measured on-device with the same bytes and the same
# indexes: ds=4 sigma=5 gives 6 stars and fails, ds=1 gives ~300 and solves in
# ~2 s against index-4117.
#
# Re-extract once at the smallest downsample when the first pass is starved on a
# small frame. Healthy frames take no extra decode pass at all, which is why this
# is preferred over making the default size-aware: that would need a probe pass
# (polaris-autosolve.sh's pick_downsample decodes at 1/8 just to read the
# dimensions) on every solve, including the full-size captures that already pick
# 4 correctly. The floor and width cap are overridable so a qualification run can
# tune them without a rebuild.
if [ "${STARVED_RETRY:-1}" != "0" ] && [ "$DOWNSAMPLE" -gt 1 ] \
   && [ "$_star_count" -lt "${STARVED_STAR_FLOOR:-25}" ] \
   && [ "$W" -lt "${STARVED_WIDTH_MAX:-3000}" ]; then
    slog "extract: starved ($_star_count stars at ds=$DOWNSAMPLE on ${W}x${H}), retrying at downsample 1 (#341)"
    "$ASTRO/polaris-extract" --jpeg "$IMG" --downsample 1 \
        --max-stars "$MAXSTARS" --stats > "$STARS" 2>&2 || {
        echo '{"solved":false,"error":"extract failed"}'; exit 3; }
    _star_count=$(grep -vc '^#' "$STARS" 2>/dev/null)
    case "$_star_count" in ''|*[!0-9]*) _star_count=0 ;; esac
    DOWNSAMPLE=1
fi

# Physical sensor width is not a required standard EXIF field. Resolve it in
# an order that is useful for every camera type:
#   explicit SENSOR_MM -> exact configured model profile -> EXIF 35 mm eq ->
#   bounded generic default. The model is metadata, never a camera allow-list.
EXIF_FOCAL=$(sed -n 's/^# exif focal-mm \([0-9][0-9.]*\).*/\1/p' "$STARS" | head -1)
EXIF_CAMERA_MODEL=$(sed -n 's/^# exif camera-model //p' "$STARS" | head -1)
EXIF_FOCAL35=$(sed -n 's/^# exif focal35-mm \([0-9][0-9.]*\).*/\1/p' "$STARS" | head -1)
PROFILE_MODEL=${CAMERA_MODEL:-$EXIF_CAMERA_MODEL}
SENSOR_SOURCE=${SENSOR_SOURCE:-}
SENSOR_ASSUMED=0

# Logged after the EXIF fields exist -- logging them earlier would report "none"
# every time, which is worse than not logging them at all.
slog "extract: $(basename "$IMG") fullres=${W}x${H} downsample=$DOWNSAMPLE stars=$_star_count (max $MAXSTARS) camera='${EXIF_CAMERA_MODEL:-none}' focal_exif=${EXIF_FOCAL:-none} focal35=${EXIF_FOCAL35:-none}"

sensor_profile_value() {
    _model=$1
    [ -n "$_model" ] && [ -r "$SENSOR_PROFILE_FILE" ] || return 0
    awk -F '\t' -v model="$_model" '
        $0 !~ /^[[:space:]]*#/ && NF >= 2 && $1 == model { print $2; exit }
    ' "$SENSOR_PROFILE_FILE" 2>/dev/null | sed -n 's/^\([0-9][0-9.]*\)$/\1/p' | head -1
}

_profile_sensor=$(sensor_profile_value "$PROFILE_MODEL")
if [ -n "$SENSOR_MM" ]; then
    SENSOR_SOURCE=override
elif [ -n "$_profile_sensor" ]; then
    SENSOR_MM=$_profile_sensor
    SENSOR_SOURCE=model-profile
elif [ -n "$EXIF_FOCAL" ] && [ -n "$EXIF_FOCAL35" ]; then
    SENSOR_MM=$(awk -v f="$EXIF_FOCAL" -v e="$EXIF_FOCAL35" \
        'BEGIN { if (f > 0 && e > 0) printf "%.6f", 36 * f / e }')
    SENSOR_SOURCE=exif-35mm-equivalent
else
    if [ "$ALLOW_DEFAULT_SENSOR" != "1" ]; then
        echo '{"solved":false,"failure_reason":"sensor_geometry_required"}'
        exit 6
    fi
    SENSOR_MM=$SENSOR_DEFAULT_MM
    SENSOR_SOURCE=generic-default
    SENSOR_ASSUMED=1
fi

if ! awk -v s="$SENSOR_MM" -v lo="$SENSOR_MIN_MM" -v hi="$SENSOR_MAX_MM" \
    'BEGIN { exit !(s >= 1 && s <= 100 && lo >= 1 && hi >= lo) }'; then
    echo '{"solved":false,"failure_reason":"invalid_sensor_geometry"}'
    exit 6
fi
SOLVE_SCALE_TOL=$INDEPENDENT_SCALE_TOL
if [ "$SENSOR_ASSUMED" = "1" ]; then
    SOLVE_SCALE_TOL=$INDEPENDENT_SCALE_TOL_ASSUMED
fi
echo "[polaris-align] sensor width: ${SENSOR_MM}mm (${SENSOR_SOURCE})${PROFILE_MODEL:+ model=$PROFILE_MODEL} assumed=$SENSOR_ASSUMED" >&2

# ---- pixel scale: EXIF first, then config, then a realistic lens range -----
#
# A WRONG FOCAL MAKES THE SOLVE IMPOSSIBLE, NOT SLOW. The scale search is
# derived from it, so a 70 mm frame searched at 400 mm hunts 2.3 arcsec/pix
# when the truth is 13.4 and no quad can ever match. An entire night of frames
# failed this way -- config said 400, the zoom was at 70. Those same frames
# solved in 5 s once the focal was right.
#
# So the frame's own EXIF wins over any configured value: a config number
# cannot follow a zoom ring. If there is no EXIF (live-view frames carry none)
# we use the configured focal, and if there is neither -- or the focal we tried
# does not solve -- we search the whole range of focal lengths that could
# plausibly be on this mount rather than guessing a single wrong one.
FOCAL_MIN=${FOCAL_MIN:-8}          # ultra-wide
FOCAL_MAX=${FOCAL_MAX:-3000}       # long telephoto; nothing realistic exceeds this

# The range search is the SAFETY NET, not the fast path: measured 148 s on this
# device versus 5 s with a known focal. It therefore gets its own, longer
# budget -- with the caller's 45 s it would always time out and the net would
# never actually catch anything.
RANGE_TIMEOUT=${RANGE_TIMEOUT:-240}

# LIVE-VIEW FRAMES CARRY NO EXIF, so without this every calibration solve would
# take the 148 s path. The lens does not change between a capture and the live
# view seconds later, so remember the last focal a real frame reported and use
# it for frames that cannot say. If the lens HAS been changed since, that focal
# simply fails to solve and we fall through to the range search anyway.
FOCAL_CACHE=${FOCAL_CACHE:-/app/sd/polaris-astro/last-focal}
if [ -n "$EXIF_FOCAL" ]; then
    mkdir -p "$(dirname "$FOCAL_CACHE")" 2>/dev/null
    printf '%s\n' "$EXIF_FOCAL" > "$FOCAL_CACHE" 2>/dev/null
fi
CACHED_FOCAL=""
[ -z "$EXIF_FOCAL" ] && [ -r "$FOCAL_CACHE" ] && \
    CACHED_FOCAL=$(sed -n 's/^\([0-9][0-9.]*\)$/\1/p' "$FOCAL_CACHE" | head -1)

# MANUAL OVERRIDE, set from the web UI, beats everything including EXIF.
# The case that needs it: a telescope or an adapted manual lens reports NO
# focal length at all (no electrical contacts), and a camera body will happily
# stamp a stale or nonsense value into EXIF for one. When somebody has taken
# the trouble to type in a number, that number is better information than
# anything we can infer, so it goes first. Delete the file to return to auto.
FOCAL_OVERRIDE_FILE=${FOCAL_OVERRIDE_FILE:-/app/sd/polaris-astro/focal-override}
[ -z "${FOCAL_OVERRIDE:-}" ] && [ -r "$FOCAL_OVERRIDE_FILE" ] && \
    FOCAL_OVERRIDE=$(sed -n 's/^\([0-9][0-9.]*\)$/\1/p' "$FOCAL_OVERRIDE_FILE" | head -1)
FOCAL_OVERRIDE=${FOCAL_OVERRIDE:-}

# Return the scale constraint for one focal estimate. With an assumed sensor
# we give Astrometry.net the full bounded sensor range, and give the independent
# solver a deliberately wider acceptance band. A verified transform still
# reports the measured scale, so this broadens admission without changing the
# final pointing geometry.
solver_scale_args() {
    _f=$1
    if [ "$SENSOR_ASSUMED" = "1" ] && [ "$SOLVER_BIN" = "polaris-solve" ]; then
        awk -v lo="$SENSOR_MIN_MM" -v hi="$SENSOR_MAX_MM" -v w="$W" -v f="$_f" \
            'BEGIN {
                if (f > 0 && w > 0) {
                    a = 206264.806 * atan2((lo / w) / f, 1) * 0.85;
                    b = 206264.806 * atan2((hi / w) / f, 1) * 1.15;
                    printf "--scale-low %.6f --scale-high %.6f", a, b;
                }
            }'
    else
        printf '%s\n' "--focal-mm $_f --sensor-mm $SENSOR_MM"
    fi
}

solve_with() {
    _scale=$1
    # Every solve in this script funnels through here -- override, EXIF,
    # configured, indexed-hint and blind alike -- so instrumenting it once covers
    # all of them. The range fallback at the end calls the solver directly and is
    # logged separately.
    _t0=$(solve_now)
    slog "solve start: bin=$SOLVER_BIN img=$(basename "$IMG") fullres=${W}x${H} ds=$DOWNSAMPLE stars=$_star_count focal=${_scale:-none} hint=${USE_HINT:-0}/${RA:-?}/${DEC:-?}/${RADIUS:-?} limit=${SOLVE_TIMEOUT}s"
    if [ "$SOLVER_BIN" != "polaris-solve" ]; then
        [ -n "$_scale" ] || { slog "solve refused: no focal for $SOLVER_BIN"; echo '{"solved":false,"failure_reason":"focal_length_required"}'; return 1; }
        if [ "$SOLVER_BIN" = "polaris-solve-independent-search" ]; then
            set -- --catalog-dir "$INDEPENDENT_CATALOG_DIR" --manifest "$INDEPENDENT_CATALOG_MANIFEST" \
                --triangle-index "$INDEPENDENT_TRIANGLE_INDEX" \
                --solver "$ASTRO/polaris-solve-independent" --stars "$STARS" --width "$W" --height "$H" \
                --max-catalog "$INDEPENDENT_MAX_CATALOG" --anchor-stars "$INDEPENDENT_ANCHOR_STARS" \
                --attempts "$INDEPENDENT_ATTEMPTS" --min-matches "${MIN_MATCHES:-12}" \
                --solver-timeout "$INDEPENDENT_SOLVER_TIMEOUT" \
                --search-timeout "$INDEPENDENT_SEARCH_TIMEOUT" \
                --scale-tol "$SOLVE_SCALE_TOL" $_scale
            # The bound that can produce failure_reason:"timeout" for this solver is
            # the search deadline, not SOLVE_TIMEOUT: polaris-solve-independent-search.c
            # emits that value only once search_deadline has passed. Naming the wrong
            # bound would attribute a timeout to a limit this solver was never given.
            _bound=$INDEPENDENT_SEARCH_TIMEOUT
        else
            set -- --catalog "$INDEPENDENT_CATALOG" --stars "$STARS" --width "$W" --height "$H" \
                --cpulimit "$SOLVE_TIMEOUT" --max-catalog "$INDEPENDENT_MAX_CATALOG" \
                --anchor-stars "$INDEPENDENT_ANCHOR_STARS" \
                --scale-tol "$SOLVE_SCALE_TOL" $_scale
            _bound=$SOLVE_TIMEOUT
        fi
        [ "$USE_HINT" = "1" ] && [ -n "$RA" ] && [ -n "$DEC" ] && [ -n "$RADIUS" ] && \
            set -- "$@" --ra "$RA" --dec "$DEC" --radius "$RADIUS"
        _out=$("$ASTRO/$SOLVER_BIN" "$@")
        _rc=$?
        solve_finish "$_t0" "$_rc" "$_out" "$_scale" "$_bound"
        printf '%s\n' "$_out"
        return $_rc
    fi
    set -- $IDXARGS --stars "$STARS" --width "$W" --height "$H" --cpulimit "$SOLVE_TIMEOUT"
    [ -n "$_scale" ] && set -- "$@" $_scale
    [ "$USE_HINT" = "1" ] && [ -n "$RA" ] && [ -n "$DEC" ] && [ -n "$RADIUS" ] && \
        set -- "$@" --ra "$RA" --dec "$DEC" --radius "$RADIUS"
    _out=$("$ASTRO/$SOLVER_BIN" "$@")
    _rc=$?
    solve_finish "$_t0" "$_rc" "$_out" "$_scale"
    printf '%s\n' "$_out"
}

# Classify one finished solve into the four outcomes #321 asks about, which look
# identical from outside: solved, timed out, found nothing, or produced nothing.
# The two solvers report a timeout with different vocabularies, and both have to
# be matched or one of them is silently misfiled:
#   polaris-solve.c                    {"solved":false,"error":"timeout"}  rc=3
#       its SIGALRM wall-clock bound (on_timeout).
#   polaris-solve-independent-search.c {"solved":false,"failure_reason":
#                                      "timeout","attempts":N,...}          rc=7
#       emitted only when search_deadline > 0 and has passed, so it is never an
#       inference -- the sibling value "search_exhausted" means every tile was
#       tried within the budget, which is a different diagnosis entirely.
# Observed on hardware with polaris-solve-independent-search: a real timeout was
# logged as "solve no match: 50.37s rc=7 ... solver said:
# {\"solved\":false,\"failure_reason\":\"timeout\",...}" because only the first
# vocabulary was matched -- exactly the confusion #321 exists to remove.
solve_finish() {
    # $_lim is the bound actually passed to this solver run, and has to be a
    # parameter rather than SOLVE_TIMEOUT: the range fallback uses RANGE_TIMEOUT
    # (240 s), so reading the global here printed "reached the 45s bound" for a
    # solve limited to 240 s. A wrong number in a diagnostic is worse than none.
    _t0=$1; _rc=$2; _out=$3; _scale=$4; _lim=${5:-$SOLVE_TIMEOUT}
    _el=$(awk -v a="$_t0" -v b="$(solve_now)" 'BEGIN{printf "%.2f", b-a}')
    _dump=0
    case "$_out" in
        *'"solved":true'*)              _v="SOLVED" ;;
        *'"error":"timeout"'*)          _v="TIMEOUT (reached the ${_lim}s bound -- may succeed with a longer one)" ;;
        *'"failure_reason":"timeout"'*) _v="TIMEOUT (search bound ${_lim}s reached after attempts, not exhausted -- may succeed with a longer one)" ;;
        *'"failure_reason":"search_exhausted"'*) _v="no match (all tiles searched within ${_lim}s -- not a timeout)"; _dump=1 ;;
        *'"solved":false'*)             _v="no match"; _dump=1 ;;
        *)                              _v="no output" ;;
    esac
    slog "solve $_v: ${_el}s rc=$_rc stars=$_star_count bin=$SOLVER_BIN${_scale:+ $_scale}"
    [ "$_dump" = 1 ] && slog "  solver said: $(printf '%s' "$_out" | tr -d '\n' | head -c 200)"
    return 0
}

# arcsec/pixel bounds implied by the focal range. Long lens -> small scale.
range_args() {
    _smin=$SENSOR_MM; _smax=$SENSOR_MM
    [ "$SENSOR_ASSUMED" = "1" ] && { _smin=$SENSOR_MIN_MM; _smax=$SENSOR_MAX_MM; }
    awk -v smin="$_smin" -v smax="$_smax" -v w="$W" -v fmin="$FOCAL_MIN" -v fmax="$FOCAL_MAX" 'BEGIN{
        lo  = 206264.806 * atan2((smin / w) / fmax, 1) * 0.9;
        hi  = 206264.806 * atan2((smax / w) / fmin, 1) * 1.1;
        printf "--scale-low %.6f --scale-high %.6f", lo, hi }'
}

TRIED=""
if [ -n "$FOCAL_OVERRIDE" ]; then
    if [ -n "$EXIF_FOCAL" ] && [ "$EXIF_FOCAL" != "$FOCAL_OVERRIDE" ]; then
        echo "[polaris-align] focal: MANUAL OVERRIDE ${FOCAL_OVERRIDE}mm (EXIF says ${EXIF_FOCAL}mm)" >&2
    else
        echo "[polaris-align] focal: MANUAL OVERRIDE ${FOCAL_OVERRIDE}mm" >&2
    fi
    TRIED="${FOCAL_OVERRIDE}mm (manual)"
    OUT=$(solve_with "$(solver_scale_args "$FOCAL_OVERRIDE")")
    case "$OUT" in *'"solved":true'*) emit_solution "$OUT"; exit 0;; esac
elif [ -n "$EXIF_FOCAL" ]; then
    if [ -n "$FOCAL" ] && [ "$FOCAL" != "$EXIF_FOCAL" ]; then
        echo "[polaris-align] focal: EXIF says ${EXIF_FOCAL}mm, config says ${FOCAL}mm -- trusting EXIF" >&2
    else
        echo "[polaris-align] focal from EXIF: ${EXIF_FOCAL}mm" >&2
    fi
    TRIED="${EXIF_FOCAL}mm (exif)"
    OUT=$(solve_with "$(solver_scale_args "$EXIF_FOCAL")")
    case "$OUT" in *'"solved":true'*) emit_solution "$OUT"; exit 0;; esac
elif [ -n "$CACHED_FOCAL" ]; then
    echo "[polaris-align] no EXIF (live view?) -- using ${CACHED_FOCAL}mm from the last frame that had it" >&2
    TRIED="${CACHED_FOCAL}mm (cached)"
    OUT=$(solve_with "$(solver_scale_args "$CACHED_FOCAL")")
    case "$OUT" in *'"solved":true'*) emit_solution "$OUT"; exit 0;; esac
    # a cached focal that no longer solves is worse than none -- drop it so we
    # do not pay for it on every subsequent frame
    rm -f "$FOCAL_CACHE" 2>/dev/null
elif [ -n "$FOCAL" ]; then
    echo "[polaris-align] focal from config: ${FOCAL}mm (frame has no EXIF)" >&2
    TRIED="${FOCAL}mm (config)"
    OUT=$(solve_with "$(solver_scale_args "$FOCAL")")
    case "$OUT" in *'"solved":true'*) emit_solution "$OUT"; exit 0;; esac
fi

[ "$SOLVER_BIN" = "polaris-solve-independent" ] && { echo '{"solved":false,"failure_reason":"independent_solver_needs_known_focal"}'; exit 6; }
[ "$SOLVER_BIN" = "polaris-solve-independent-search" ] && {
    SEARCH_FOCAL=${FOCAL:-${EXIF_FOCAL:-}}
    [ -n "$SEARCH_FOCAL" ] || { echo '{"solved":false,"failure_reason":"independent_solver_needs_known_focal"}'; exit 6; }
    [ -n "${OUT:-}" ] || OUT=$(solve_with "$(solver_scale_args "$SEARCH_FOCAL")")
    case "$OUT" in
        *'"solved":true'*) emit_solution "$OUT"; exit 0;;
    esac
    if [ "$USE_HINT" = "1" ] && [ -n "$RA" ] && [ -n "$DEC" ]; then
        if [ "$INDEPENDENT_BLIND_FALLBACK" = "1" ]; then
            echo "[polaris-align] indexed hint search failed -- retrying bounded blind search (explicitly enabled)" >&2
            USE_HINT=0
            OUT=$(solve_with "$(solver_scale_args "$SEARCH_FOCAL")")
        else
            echo "[polaris-align] indexed hint search failed -- blind fallback disabled" >&2
        fi
    fi
    case "$OUT" in *'"solved":true'*) emit_solution "$OUT";; *) echo "$OUT";; esac
    exit 0
}
[ -n "$TRIED" ] && echo "[polaris-align] $TRIED did not solve -- retrying across ${FOCAL_MIN}-${FOCAL_MAX}mm" >&2
[ -n "$TRIED" ] || echo "[polaris-align] no focal known -- searching ${FOCAL_MIN}-${FOCAL_MAX}mm" >&2
# This path bypasses solve_with, so it is timed and classified here too. It uses
# RANGE_TIMEOUT rather than SOLVE_TIMEOUT, which is why the limit is printed: a
# reader needs to know which bound was hit.
_rt0=$(solve_now)
slog "solve start: bin=$SOLVER_BIN img=$(basename "$IMG") fullres=${W}x${H} ds=$DOWNSAMPLE stars=$_star_count focal=range ${FOCAL_MIN}-${FOCAL_MAX}mm hint=${USE_HINT:-0}/${RA:-?}/${DEC:-?}/${RADIUS:-?} limit=${RANGE_TIMEOUT}s"
OUT=$("$ASTRO/$SOLVER_BIN" $(range_args) $IDXARGS --stars "$STARS" \
     --width "$W" --height "$H" --cpulimit "$RANGE_TIMEOUT" \
     ${RA:+--ra "$RA"} ${DEC:+--dec "$DEC"} ${RADIUS:+--radius "$RADIUS"})
_rc=$?
solve_finish "$_rt0" "$_rc" "$OUT" "range ${FOCAL_MIN}-${FOCAL_MAX}mm" "$RANGE_TIMEOUT"
case "$OUT" in *'"solved":true'*) emit_solution "$OUT";; *) echo "$OUT";; esac
