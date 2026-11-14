#!/bin/sh
# ============================================================================
#  #342 -- capture-to-result stage breakdown, run ON the Polaris.
#
#      scp tools/bench-capture-to-result.sh root@192.168.0.1:/tmp/
#      ssh root@192.168.0.1 'sh /tmp/bench-capture-to-result.sh'
#
#  Read-only: invokes only the shipped polaris-extract / polaris-solve and writes
#  nothing outside /tmp. Times with /proc/uptime because busybox date has no %N on
#  this device (verified: `date +%s.%N` prints the literal ".%N"), and wall-clock
#  is what a user waits for anyway.
#
#  Why this exists: #342 asks where the time actually goes before anything is
#  optimised. polaris-solve only ever timed solver_run(), so extraction -- which
#  turns out to be nearly half the wait -- was invisible.
# ============================================================================
IMG=${1:-/app/sd/test-input/upload-1794522364-704-G7D9gnBg.jpeg}
A=/app/astro
IDX=${2:-/app/sd/astrometry}

IDXARGS=""
for f in "$IDX"/index-*.fits; do
    [ -f "$f" ] && IDXARGS="$IDXARGS --index $f"
done

now() { cut -d' ' -f1 /proc/uptime; }

# elapsed_ms START END -> ms difference, integer
elapsed_ms() {
    awk -v a="$1" -v b="$2" 'BEGIN { printf "%d", (b - a) * 1000 + 0.5 }'
}

echo "== device =="
grep -m1 'model name' /proc/cpuinfo | sed 's/^/  cpu: /'
grep -c ^processor /proc/cpuinfo | sed 's/^/  cores: /'
sed 's/^/  uptime-load: /' /proc/loadavg

echo "== indexes =="
ls "$IDX"/index-*.fits 2>/dev/null | wc -l | sed 's/^/  count: /'
du -ch "$IDX"/index-*.fits 2>/dev/null | tail -1 | awk '{print "  total: "$1}'

echo "== per-stage, real shipped binaries =="
for i in 1 2 3; do
    s0=$(now)
    "$A/polaris-extract" --jpeg "$IMG" --downsample 1 --max-stars 200 --stats > /tmp/b342.stars 2>/dev/null
    s1=$(now)
    n=$(grep -vc '^#' /tmp/b342.stars)
    s2=$(now)
    "$A/polaris-solve" $IDXARGS --stars /tmp/b342.stars --width 1920 --height 1280 \
        --cpulimit 45 > /tmp/b342.json 2>/dev/null
    rc=$?
    s3=$(now)
    ex=$(elapsed_ms "$s0" "$s1")
    sv=$(elapsed_ms "$s2" "$s3")
    tot=$(elapsed_ms "$s0" "$s3")
    solved=$(sed -n 's/.*"solved":\([a-z]*\).*/\1/p' /tmp/b342.json | head -1)
    echo "  run$i: extract=${ex}ms stars=$n solve=${sv}ms total=${tot}ms rc=$rc solved=${solved:-none}"
done

echo "== solver's own stage split (needs --timings; deployed binary predates it) =="
"$A/polaris-solve" --help 2>&1 | grep -c -- '--timings' | sed 's/^/  --timings supported: /'
sed -n 's/.*"solve_seconds":\([0-9.]*\).*/  deployed solve_seconds: \1/p' /tmp/b342.json | head -1

rm -f /tmp/b342.stars /tmp/b342.json
