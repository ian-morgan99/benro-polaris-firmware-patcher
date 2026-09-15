#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WRAPPER=$ROOT/container/ondisk/pgphoto.wrapper.in
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

mkdir -p "$TMP/stage2/libgphoto2/2.5.34" "$TMP/stage2/libgphoto2_port/0.12.2"
cat > "$TMP/stage2/pgphoto.stage2ondisk" <<'EOF'
#!/bin/sh
echo launched
echo "preview_backoff=$STAGE2_PENTAX_PREVIEW_BACKOFF"
echo "preview_interval=$STAGE2_PENTAX_PREVIEW_MIN_INTERVAL_SECS"
EOF
chmod +x "$TMP/stage2/pgphoto.stage2ondisk"

run_wrapper() {
    OPENPOLARIS_RUN_DIR=$TMP/run \
    OPENPOLARIS_PROC_ROOT=$TMP/proc \
    OPENPOLARIS_STAGE2_DIR=$TMP/stage2 \
    OPENPOLARIS_PRINTK_PATH=$TMP/printk \
    sh "$WRAPPER"
}

mkdir -p "$TMP/proc"
printf '7 4 1 7\n' > "$TMP/printk"
mkdir -p "$TMP/run/openpolaris-pgphoto.launch.lock"
echo 999999 > "$TMP/run/openpolaris-pgphoto.launch.lock/pid"
OUT=$(run_wrapper 2>&1)
printf '%s\n' "$OUT" | grep -q 'reclaiming stale pgphoto launch lock'
printf '%s\n' "$OUT" | grep -q '^launched$'
printf '%s\n' "$OUT" | grep -q '^preview_backoff=1$'
printf '%s\n' "$OUT" | grep -q '^preview_interval=2$'
test ! -e "$TMP/run/openpolaris-pgphoto.launch.lock"

# A live but unrelated PID is stale ownership (PID reuse); it must not wedge
# every future launch.
rm -f "$TMP/run/openpolaris-pgphoto.pid" "$TMP/run/openpolaris-pgphoto.backoff"
mkdir -p "$TMP/run/openpolaris-pgphoto.launch.lock"
echo $$ > "$TMP/run/openpolaris-pgphoto.launch.lock/pid"
mkdir -p "$TMP/proc/$$"
printf '%s\0' /bin/sh > "$TMP/proc/$$/cmdline"
OUT=$(run_wrapper 2>&1)
printf '%s\n' "$OUT" | grep -q 'reclaiming stale pgphoto launch lock'
printf '%s\n' "$OUT" | grep -q '^launched$'

# A live owner whose executable is the exact stage-2 binary is genuine and is
# preserved.
rm -f "$TMP/run/openpolaris-pgphoto.pid" "$TMP/run/openpolaris-pgphoto.backoff"
mkdir -p "$TMP/run/openpolaris-pgphoto.launch.lock"
echo $$ > "$TMP/run/openpolaris-pgphoto.launch.lock/pid"
printf '%s\0' "$TMP/stage2/pgphoto.stage2ondisk" > "$TMP/proc/$$/cmdline"
OUT=$(run_wrapper 2>&1)
printf '%s\n' "$OUT" | grep -q "launch is already in progress (PID $$)"
test -d "$TMP/run/openpolaris-pgphoto.launch.lock"

# --- issue #34 TA review regression: a TERM during the backoff sleep must
# terminate the wrapper BEFORE it can publish a PID / exec a new pgphoto
# instance.  Seed the backoff file so DELAY=5, run the wrapper in the
# background, send TERM ~2 s into the backoff, and assert: (a) exit code 143,
# (b) the "backing off" path was taken, (c) no PID file was published, and
# (d) the fake stage-2 binary never launched. ---
rm -rf "$TMP/run/openpolaris-pgphoto.launch.lock"   # clear the live-owner lock from the previous section
rm -f "$TMP/run/openpolaris-pgphoto.pid"
NOW=$(date +%s)
echo "0 $NOW" > "$TMP/run/openpolaris-pgphoto.backoff"   # -> COUNT=1, DELAY=5
OUTF="$TMP/term-during-backoff.out"
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_STAGE2_DIR=$TMP/stage2 OPENPOLARIS_PRINTK_PATH=$TMP/printk \
    sh "$WRAPPER" >"$OUTF" 2>&1 &
WPID=$!
sleep 2
kill -TERM "$WPID" 2>/dev/null || true
rc=0
wait "$WPID" || rc=$?
test "$rc" = "143"
printf '%s\n' "$(cat "$OUTF")" | grep -q 'backing off'
test ! -e "$TMP/run/openpolaris-pgphoto.pid"
! printf '%s\n' "$(cat "$OUTF")" | grep -q '^launched$'

# The default containment changes only console loglevel, and opt-out preserves
# the original value. The fake file makes this safe and deterministic.
test "$(cat "$TMP/printk")" = "1"
printf '7 4 1 7\n' > "$TMP/printk"
rm -rf "$TMP/run/openpolaris-pgphoto.launch.lock"
rm -f "$TMP/run/openpolaris-pgphoto.pid" "$TMP/run/openpolaris-pgphoto.backoff"
OPENPOLARIS_PRINTK_QUIET=0 run_wrapper >/dev/null 2>&1
test "$(cat "$TMP/printk")" = "7 4 1 7"

echo 'PASS: pgphoto wrapper validates lock ownership, contains console log floods, and exits safely during backoff (issue #34)'
