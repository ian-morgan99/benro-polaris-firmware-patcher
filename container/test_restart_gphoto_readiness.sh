#!/bin/sh
# Regression test for issue #253: a slow but progressing camera init must not
# be mistaken for a dead pgphoto process, while a genuinely hung init must
# still fail within the configured bounded readiness window.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RESTART=$ROOT/container/ondisk/restart_gphoto.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

PROC=$TMP/proc
RUN=$TMP/run
LOGF=$TMP/clog.txt
BIN=/app/lib/stage2/pgphoto.stage2ondisk
LAUNCHES=$TMP/launches
mkdir -p "$PROC/net" "$RUN"
printf '0\n' > "$LAUNCHES"

cat > "$TMP/wrapper-slow" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
COUNT="$OPENPOLARIS_LAUNCH_COUNT"
mkdir -p "$PR/$$"
printf '%s' "$BIN" > "$PR/$$/cmdline"
count=$(cat "$COUNT" 2>/dev/null || printf '0')
printf '%s\n' $((count + 1)) > "$COUNT"
(
    # This deliberately exceeds the old production 20-second bound.  The
    # regression must be red on the parent revision, not merely prove that a
    # three-second delay fits inside both the old and new implementations.
    sleep 21
    printf '  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A\n' > "$PR/net/tcp"
) &
trap 'rm -f "$PR/net/tcp"; rm -rf "$PR/$$"; exit 0' TERM INT
while :; do sleep 0.2; done
EOF

cat > "$TMP/wrapper-hung" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
COUNT="$OPENPOLARIS_LAUNCH_COUNT"
mkdir -p "$PR/$$"
printf '%s' "$BIN" > "$PR/$$/cmdline"
count=$(cat "$COUNT" 2>/dev/null || printf '0')
printf '%s\n' $((count + 1)) > "$COUNT"
trap 'rm -rf "$PR/$$"; exit 0' TERM INT
while :; do sleep 0.2; done
EOF
chmod +x "$TMP/wrapper-slow" "$TMP/wrapper-hung"

run_restart() {
    wrapper=$1
    output=$2
    OPENPOLARIS_RUN_DIR="$RUN" \
    OPENPOLARIS_PROC_ROOT="$PROC" \
    OPENPOLARIS_PGPHOTO_WRAPPER="$wrapper" \
    OPENPOLARIS_PGPHOTO_BINARY="$BIN" \
    OPENPOLARIS_PGPHOTO_LOG="$LOGF" \
    OPENPOLARIS_LAUNCH_COUNT="$LAUNCHES" \
        sh "$RESTART" > "$output" 2>&1
}

run_restart_bounded() {
    wrapper=$1
    output=$2
    wait_max=$3
    OPENPOLARIS_RUN_DIR="$RUN" \
    OPENPOLARIS_PROC_ROOT="$PROC" \
    OPENPOLARIS_PGPHOTO_WRAPPER="$wrapper" \
    OPENPOLARIS_PGPHOTO_BINARY="$BIN" \
    OPENPOLARIS_PGPHOTO_LOG="$LOGF" \
    OPENPOLARIS_LAUNCH_COUNT="$LAUNCHES" \
    OPENPOLARIS_PGPHOTO_START_WAIT_MAX="$wait_max" \
        sh "$RESTART" > "$output" 2>&1
}

cleanup_launched() {
    if [ -f "$RUN/openpolaris-pgphoto.pid" ]; then
        pid=$(cat "$RUN/openpolaris-pgphoto.pid" 2>/dev/null || true)
        case "$pid" in ''|*[!0-9]*) pid= ;; esac
        [ -z "$pid" ] || kill "$pid" 2>/dev/null || true
    fi
    rm -f "$RUN/openpolaris-pgphoto.pid" "$PROC/net/tcp"
    rm -rf "$PROC"/[0-9]*
}

# A slow init publishes readiness after 21 seconds, beyond the old production
# 20-second bound. The fixed helper must wait for the real listener and
# succeed, and it must launch pgphoto only once while doing so.
OUT_SLOW=$TMP/slow.out
run_restart "$TMP/wrapper-slow" "$OUT_SLOW"
grep -q 'OK: port 8080 listening' "$OUT_SLOW"
test "$(cat "$LAUNCHES")" = 1
cleanup_launched

# A process that never publishes readiness must still fail closed at an
# explicitly configured one-second bound. Measuring the elapsed wall time makes
# the override assertion fail against the old hard-coded 20-second helper.
printf '0\n' > "$LAUNCHES"
OUT_HUNG=$TMP/hung.out
STARTED=$(date +%s)
rc=0
run_restart_bounded "$TMP/wrapper-hung" "$OUT_HUNG" 1 || rc=$?
FINISHED=$(date +%s)
test "$rc" -ne 0
test "$((FINISHED - STARTED))" -lt 5
grep -q 'FAIL: pgphoto stayed alive but port 8080 did not become ready' "$OUT_HUNG"
test "$(cat "$LAUNCHES")" = 1
cleanup_launched

echo 'PASS: restart_gphoto waits for slow readiness but fails closed on hung startup (issue #253)'
