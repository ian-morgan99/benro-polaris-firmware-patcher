#!/bin/sh
# ============================================================================
#  #342 -- reproducible capture-to-result benchmark for the Polaris head.
#
#      scp tools/bench-capture-to-result.sh root@192.168.0.1:/tmp/
#      ssh root@192.168.0.1 'sh /tmp/bench-capture-to-result.sh' > bench.jsonl
#      COLD=1 ssh ... 'COLD=1 sh /tmp/bench-capture-to-result.sh' > cold.jsonl
#
#  Emits JSONL: one "meta" record describing machine/binaries/indexes, then one
#  "run" record per measured solve. Machine-readable on purpose -- #342 asks for
#  CSV/JSON plus a bottleneck-ranked recommendation, and prose in a log cannot be
#  diffed across firmware versions.
#
#  Read-only. Invokes only the shipped polaris-extract / polaris-solve, writes
#  nothing outside /tmp, and never touches a deployed file or any camera path.
#
#  Timing uses /proc/uptime: busybox date has no %N on this head (verified --
#  `date +%s.%N` prints the literal ".%N"). These are wall-clock figures because
#  that is what a user waits for; #342 warns against confusing CPU with wall time,
#  and the solver's own getrusage peak_rss_kb is reported separately from elapsed.
# ============================================================================

IMG=${1:-/app/sd/test-input/upload-1794522364-704-G7D9gnBg.jpeg}
A=${ASTRO:-/app/astro}
IDX=${INDEXES:-/app/sd/astrometry}
RUNS=${RUNS:-3}
DOWNSAMPLE=${DOWNSAMPLE:-1}
MAXSTARS=${MAXSTARS:-200}
CPULIMIT=${CPULIMIT:-45}

now() { cut -d' ' -f1 /proc/uptime; }
ms()  { awk -v a="$1" -v b="$2" 'BEGIN { printf "%d", (b - a) * 1000 + 0.5 }'; }
jstr() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

have_timings=0
"$A/polaris-solve" --help 2>&1 | grep -q -- '--timings' && have_timings=1

IDXARGS=""
_nidx=0
for f in "$IDX"/index-*.fits; do
    [ -f "$f" ] || continue
    IDXARGS="$IDXARGS --index $f"
    _nidx=$((_nidx + 1))
done

_cpu=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')
_cores=$(grep -c ^processor /proc/cpuinfo)
_total_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
_free_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
_load=$(cut -d' ' -f1-3 /proc/loadavg)
_img_sz=$(stat -c %s "$IMG" 2>/dev/null || echo 0)
_img_md5=$(md5sum "$IMG" 2>/dev/null | cut -d' ' -f1)
_solv_md5=$(md5sum "$A/polaris-solve" 2>/dev/null | cut -d' ' -f1)
_ext_md5=$(md5sum "$A/polaris-extract" 2>/dev/null | cut -d' ' -f1)
# Sum sizes with stat. BusyBox du has no -cb, and reading the files (cat | wc -c)
# would pull all 44 MB into the page cache and corrupt a subsequent COLD=1 run.
_idx_bytes=0
for f in "$IDX"/index-*.fits; do
    [ -f "$f" ] || continue
    _sz=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f" 2>/dev/null || echo 0)
    _idx_bytes=$((_idx_bytes + _sz))
done

printf '{"record":"meta","image":"%s","image_bytes":%s,"image_md5":"%s",' \
    "$(jstr "$IMG")" "$_img_sz" "$_img_md5"
printf '"astro_dir":"%s","index_dir":"%s","indexes":%s,"index_bytes":%s,' \
    "$(jstr "$A")" "$(jstr "$IDX")" "$_nidx" "${_idx_bytes:-0}"
printf '"polaris_solve_md5":"%s","polaris_extract_md5":"%s","timings_supported":%s,' \
    "$_solv_md5" "$_ext_md5" "$have_timings"
printf '"cpu":"%s","cores":%s,"mem_total_kb":%s,"mem_available_kb":%s,"load1":"%s",'\
    "$(jstr "$_cpu")" "$_cores" "$_total_kb" "$_free_kb" "$_load"
printf '"downsample":%s,"max_stars":%s,"cpulimit_s":%s,"runs":%s}\n' \
    "$DOWNSAMPLE" "$MAXSTARS" "$CPULIMIT" "$RUNS"

for i in $(seq 1 "$RUNS"); do
    cold=0
    if [ "${COLD:-0}" = "1" ] && [ -w /proc/sys/vm/drop_caches ]; then
        sync
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null && cold=1
    fi

    s0=$(now)
    "$A/polaris-extract" --jpeg "$IMG" --downsample "$DOWNSAMPLE" \
        --max-stars "$MAXSTARS" --stats > /tmp/b.stars 2>/dev/null
    s1=$(now)
    stars=$(grep -vc '^#' /tmp/b.stars 2>/dev/null || echo 0)
    fullres=$(sed -n 's/^# full resolution *\([0-9]*\) *x *\([0-9]*\).*/\1x\2/p' /tmp/b.stars | head -1)
    W=$(echo "$fullres" | cut -dx -f1); H=$(echo "$fullres" | cut -dx -f2)

    s2=$(now)
    if [ "$have_timings" = 1 ]; then
        "$A/polaris-solve" $IDXARGS --stars /tmp/b.stars \
            --width "$W" --height "$H" --cpulimit "$CPULIMIT" --timings > /tmp/b.json 2>/dev/null
    else
        "$A/polaris-solve" $IDXARGS --stars /tmp/b.stars \
            --width "$W" --height "$H" --cpulimit "$CPULIMIT" > /tmp/b.json 2>/dev/null
    fi
    rc=$?
    s3=$(now)

    solved=$(sed -n 's/.*"solved":\([a-z]*\).*/\1/p' /tmp/b.json | head -1)
    [ -n "$solved" ] || solved=false
    idx_used=$(sed -n 's|.*/index-\([0-9]*\)\.fits.*|\1|p' /tmp/b.json | head -1)
    logodds=$(sed -n 's/.*"logodds":\([0-9.-]*\).*/\1/p' /tmp/b.json | head -1)
    nmatch=$(sed -n 's/.*"nmatch":\([0-9]*\).*/\1/p' /tmp/b.json | head -1)
    rss_kb=$(sed -n 's/.*"peak_rss_kb":\([0-9-]*\).*/\1/p' /tmp/b.json | head -1)
    t_star=$(sed -n 's/.*"star_read":\([0-9.]*\).*/\1/p' /tmp/b.json | head -1)
    t_index=$(sed -n 's/.*"index_load":\([0-9.]*\).*/\1/p' /tmp/b.json | head -1)
    t_solve=$(sed -n 's/.*"solve":\([0-9.]*\).*/\1/p' /tmp/b.json | head -1)

    printf '{"record":"run","i":%s,"cold_cache":%s,"downsample":%s,' "$i" "$cold" "$DOWNSAMPLE"
    printf '"fullres":"%s","stars":%s,"solved":%s,"rc":%s,' "$fullres" "$stars" "$solved" "$rc"
    [ -n "$idx_used" ] && printf '"index_used":"%s",' "$idx_used"
    [ -n "$logodds" ]  && printf '"logodds":%s,' "$logodds"
    [ -n "$nmatch" ]   && printf '"nmatch":%s,' "$nmatch"
    printf '"extract_ms":%s,"total_ms":%s,' "$(ms "$s0" "$s1")" "$(ms "$s0" "$s3")"
    [ -n "$t_star" ]   && printf '"star_read_ms":%s,' "$t_star"
    [ -n "$t_index" ]  && printf '"index_load_ms":%s,' "$t_index"
    [ -n "$t_solve" ]  && printf '"quad_search_ms":%s,' "$t_solve"
    [ -n "$rss_kb" ]   && printf '"peak_rss_kb":%s,' "$rss_kb"
    printf '"free_mem_kb_after":%s}\n' "$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
done

rm -f /tmp/b.stars /tmp/b.json
