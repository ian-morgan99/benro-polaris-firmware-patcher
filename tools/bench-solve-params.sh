#!/bin/sh
# #344: measure how solver parameters trade solve time against success.
#
# After the extraction hoist (b820b25) quad search became the dominant stage at ~50% of
# capture-to-result, so this is where the remaining headroom is. It sweeps the three knobs
# that actually change quad-search cost -- --depth, star count, and the scale bounds -- and
# records for each combination whether it still solved, how long the quad search took, and
# how confident the match was (logodds/nmatch).
#
# Success matters as much as speed here. A parameter set that halves solve time but fails to
# find a solution is not an optimisation, so every cell records solved/unsolved rather than
# timing alone. logodds and nmatch are captured too: if a faster setting still solves but with
# markedly lower confidence, that is a quality regression the timing alone would hide.
#
# Runs on the head (BusyBox sh). Emits JSONL so results can be diffed across firmware
# versions, like bench-capture-to-result.sh. Nothing deployed is touched: star lists are
# written under /tmp.
#
#   ASTRO=/app/astro IDX=/app/sd/astrometry \
#     STARS_SRC=/app/sd/test-input/upload-....jpeg FOCAL=50 SENSOR=36 \
#     sh bench-solve-params.sh
#
# With FOCAL/SENSOR given, the scale bounds come from the lens rather than a blind search --
# which is the realistic production path and the one #344 asks about. Set BLIND=1 to sweep
# the unconstrained case instead.

set -e

ASTRO=${ASTRO:-/app/astro}
IDX=${IDX:-/app/sd/astrometry}
STARS_SRC=${STARS_SRC:?set STARS_SRC to a jpeg with stars}
FOCAL=${FOCAL:-0}
SENSOR=${SENSOR:-36}
BLIND=${BLIND:-0}
DEPTH_LIST=${DEPTH_LIST:-"0 1 2 3"}
STAR_LIST=${STAR_LIST:-"50 100 200 300"}
RUNS=${RUNS:-2}
CPULIMIT=${CPULIMIT:-45}
WORK=${WORK:-/tmp/sweep-$$}

SOLVE="$ASTRO/polaris-solve"
EXTRACT="$ASTRO/polaris-extract"
[ -x "$SOLVE" ] || { echo "no solver at $SOLVE" >&2; exit 1; }
[ -x "$EXTRACT" ] || { echo "no extractor at $EXTRACT" >&2; exit 1; }

mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT INT TERM

now_ms() { cut -d' ' -f1 /proc/uptime | awk '{printf "%d", $1*1000+0.5}'; }

# Does this build report per-stage timings? Probed once rather than assumed, so an older
# binary degrades to total-only instead of failing on an unknown option.
if "$SOLVE" --help 2>&1 | grep -q -- '--timings'; then TIMINGS=1; else TIMINGS=0; fi

_idx_bytes=0
for f in "$IDX"/index-*.fits; do
    [ -f "$f" ] || continue
    _sz=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f" 2>/dev/null || echo 0)
    _idx_bytes=$((_idx_bytes + _sz))
done

printf '{"record":"meta","image":"%s","astro_dir":"%s","index_dir":"%s","indexes":%d,"index_bytes":%d,"polaris_solve_md5":"%s","timings_supported":%d,"focal_mm":%s,"sensor_mm":%s,"blind":%d,"cpulimit_s":%s,"runs":%d,"cpu":"%s","cores":%s}\n' \
    "$STARS_SRC" "$ASTRO" "$IDX" "$(ls "$IDX"/index-*.fits 2>/dev/null | wc -l)" \
    "$_idx_bytes" "$(md5sum "$SOLVE" 2>/dev/null | cut -c1-32)" "$TIMINGS" \
    "$FOCAL" "$SENSOR" "$BLIND" "$CPULIMIT" "$RUNS" \
    "$(grep -m1 'Processor' /proc/cpuinfo | sed 's/.*: //' | tr -d '"')" \
    "$(grep -c ^processor /proc/cpuinfo)"

# Build one star list per requested count, at ds=1 (the setting #341 settled on).
for n in $STAR_LIST; do
    "$EXTRACT" --jpeg "$STARS_SRC" --downsample 1 --max-stars "$n" \
        > "$WORK/stars-$n.txt" 2>/dev/null || true
done

# Full-resolution frame size, taken from the header of the star list we just built.
# polaris-extract prints "# full resolution 1920 x 1280" on stdout; the coordinates below it
# are in that same full-resolution space at ds=1, which is what the solver expects.
hdr=$(grep -m1 '^# full resolution' "$WORK/stars-$(echo "$STAR_LIST" | awk '{print $1}').txt" 2>/dev/null || true)
FW=$(printf '%s' "$hdr" | sed -n 's/.*resolution[[:space:]]*\([0-9]*\)[[:space:]]*x[[:space:]]*\([0-9]*\).*/\1/p')
FH=$(printf '%s' "$hdr" | sed -n 's/.*resolution[[:space:]]*\([0-9]*\)[[:space:]]*x[[:space:]]*\([0-9]*\).*/\2/p')
if [ -z "$FW" ] || [ -z "$FH" ]; then
    echo "could not read frame size from star list header (got: '$hdr')" >&2
    exit 1
fi

idx_args=""
for f in "$IDX"/index-*.fits; do
    [ -f "$f" ] && idx_args="$idx_args --index $f"
done

# Scale bounds: lens-derived or blind.
if [ "$BLIND" = 1 ] || [ "$FOCAL" = 0 ]; then
    scale_args=""
else
    scale_args="--focal-mm $FOCAL --sensor-mm $SENSOR"
fi

if [ "$TIMINGS" = 1 ]; then TIMING_ARG=--timings; else TIMING_ARG=""; fi

for n in $STAR_LIST; do
    sl="$WORK/stars-$n.txt"
    # grep -vc prints "0" AND exits 1 when nothing matches, so `|| echo 0` would append a
    # second line and put "0\n0" into the JSON. Take the count alone and default separately.
    got=$(grep -vc '^#' "$sl" 2>/dev/null || true)
    [ -n "$got" ] || got=0
    for d in $DEPTH_LIST; do
        best=""
        for i in $(seq 1 "$RUNS"); do
            s=$(now_ms)
            out=$("$SOLVE" $idx_args --stars "$sl" --width "$FW" --height "$FH" \
                  $scale_args --depth "$d" --cpulimit "$CPULIMIT" $TIMING_ARG 2>/dev/null || true)
            e=$(now_ms)
            el=$((e - s))
            solved=0; idx_used=""; logodds=""; nm=""
            case "$out" in *'"solved":true'*) solved=1 ;; esac
            idx_used=$(printf '%s' "$out" | sed -n 's/.*"index":"\([^"]*\)".*/\1/p' | head -1)
            logodds=$(printf '%s' "$out" | sed -n 's/.*"logodds":\([0-9.eE+-]*\).*/\1/p' | head -1)
            nm=$(printf '%s' "$out" | sed -n 's/.*"match":\([0-9]*\).*/\1/p' | head -1)
            # The solver's --timings tail is timings_ms{star_read,index_load,solve}. There is no
# per-stage breakdown inside the quad search itself, so "solve" is the closest proxy and is
# reported under that name rather than being mislabelled as quad-search time.
qs=$(printf '%s' "$out" | sed -n 's/.*"solve":\([0-9.]*\)}.*/\1/p' | head -1)
iload=$(printf '%s' "$out" | sed -n 's/.*"index_load":\([0-9.]*\).*/\1/p' | head -1)
            # Keep the fastest successful run; on failure keep the first for reference.
            # Written as plain ifs: `[ cond ] && cmd` returns 1 when cond is false, which
            # under set -e aborts the whole sweep on the second iteration.
            if [ -z "$best" ]; then
                best="$el|$solved|$idx_used|$logodds|$nm|$qs|$iload"
            elif [ "$solved" = 1 ]; then
                bt=$(printf '%s' "$best" | cut -d'|' -f1)
                bs=$(printf '%s' "$best" | cut -d'|' -f2)
                # Prefer a success over a timeout, then the faster success. Without the
                # solved-first rule a cell that timed out quickly would be reported as
                # "best" ahead of a slower run that actually found the answer.
                if [ "$bs" != 1 ] || [ "$el" -lt "$bt" ]; then
                    best="$el|$solved|$idx_used|$logodds|$nm|$qs|$iload"
                fi
            fi
        done
        t=$(printf '%s' "$best" | cut -d'|' -f1)
        sv=$(printf '%s' "$best" | cut -d'|' -f2)
        ix=$(printf '%s' "$best" | cut -d'|' -f3)
        lo=$(printf '%s' "$best" | cut -d'|' -f4)
        mm=$(printf '%s' "$best" | cut -d'|' -f5)
        qsv=$(printf '%s' "$best" | cut -d'|' -f6)
        ilv=$(printf '%s' "$best" | cut -d'|' -f7)
        # A cell that ran to the wall-clock limit is a timeout, not a fast solve. Marking it
        # explicitly keeps "total_ms: 24060" from being read as a legitimate result.
        hit=0
        if [ "$sv" != 1 ] && [ "$t" -ge $((CPULIMIT * 1000 - 500)) ]; then hit=1; fi
        printf '{"record":"cell","stars":%s,"stars_detected":%s,"depth":%s,"blind":%s,"solved":%s,"timed_out":%s,"total_ms":%s,"solve_ms":%s,"index_load_ms":%s,"index_used":"%s","logodds":%s,"match":%s}\n' \
            "$n" "$got" "$d" "$BLIND" "$sv" "$hit" "$t" "${qsv:-null}" "${ilv:-null}" "$ix" "${lo:-null}" "${mm:-null}"
    done
done
