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
mkdir -p "$PROC/net" "$RUN"

cat > "$TMP/wrapper-slow" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
mkdir -p "$PR/$$"
printf '%s' "$BIN" > "$PR/$$/cmdline"
(
    # Exceed the old 20-second loop plus its two-second initial check.
    sleep 24 & sleeper=$!
    trap 'wait "$sleeper" 2>/dev/null || :; exit 0' TERM INT
    wait "$sleeper"
    printf '  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A\n' > "$PR/net/tcp"
) &
child=$!
printf '%s\n' "$child" > "$OPENPOLARIS_TEST_CHILD_FILE"
trap 'wait "$child" "$sleeper" 2>/dev/null || :; rm -f "$PR/net/tcp"; rm -rf "$PR/$$"; exit 0' TERM INT
while :; do sleep 0.2 & sleeper=$!; wait "$sleeper" || :; done
EOF

cat > "$TMP/wrapper-hung" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
mkdir -p "$PR/$$"
printf '%s' "$BIN" > "$PR/$$/cmdline"
trap 'wait "$sleeper" 2>/dev/null || :; rm -rf "$PR/$$"; exit 0' TERM INT
while :; do sleep 0.2 & sleeper=$!; wait "$sleeper" || :; done
EOF
cat > "$TMP/wrapper-dies" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
mkdir -p "$PR/$$"
printf '%s' "$BIN" > "$PR/$$/cmdline"
(
    sleep 3 & sleeper=$!
    trap 'wait "$sleeper" 2>/dev/null || :; exit 0' TERM INT
    wait "$sleeper"
    printf '  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A\n' > "$PR/net/tcp"
) &
child=$!
printf '%s\n' "$child" > "$OPENPOLARIS_TEST_CHILD_FILE"
sleep 2.5 & sleeper=$!
trap 'wait "$child" "$sleeper" 2>/dev/null || :; rm -rf "$PR/$$"; exit 0' TERM INT
wait "$sleeper"
rm -rf "$PR/$$"
exit 0
EOF
chmod +x "$TMP/wrapper-slow" "$TMP/wrapper-hung" "$TMP/wrapper-dies"

run_restart() {
    wrapper=$1
    output=$2
    OPENPOLARIS_RUN_DIR="$RUN" \
    OPENPOLARIS_PROC_ROOT="$PROC" \
    OPENPOLARIS_PGPHOTO_WRAPPER="$wrapper" \
    OPENPOLARIS_PGPHOTO_BINARY="$BIN" \
    OPENPOLARIS_PGPHOTO_LOG="$LOGF" \
    OPENPOLARIS_TEST_CHILD_FILE="$TMP/child.pid" \
    OPENPOLARIS_PGPHOTO_START_WAIT_MAX="${TEST_WAIT_MAX:-90}" \
        sh "$RESTART" > "$output" 2>&1
}

stop_test_process() {
    pid=$1
    case "$pid" in ''|*[!0-9]*) return ;; esac
    [ -r "/proc/$pid/cmdline" ] || return 0
    cmd=$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null || true)
    # Match only this test's uniquely named wrapper, never an arbitrary PID.
    case "$cmd" in
        "/bin/sh
$TMP/wrapper-slow"|"/bin/sh
$TMP/wrapper-hung"|"/bin/sh
$TMP/wrapper-dies") kill "$pid" 2>/dev/null || true ;;
        *) return 0 ;;
    esac
    # The fake wrapper reaps its own short-lived children before exiting.
    # Recheck the unique command line while waiting; do not remove fixtures
    # or begin another case while that same process is still running.
    i=0
    while [ "$i" -lt 28 ]; do
        [ -r "/proc/$pid/cmdline" ] || return 0
        current=$(tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null || true)
        [ "$current" = "$cmd" ] || return 0
        sleep 1
        i=$((i + 1))
    done
    echo "test wrapper $pid did not exit; preserving test files" >&2
    return 1
}

cleanup_launched() {
    if [ -f "$RUN/openpolaris-pgphoto.pid" ]; then
        stop_test_process "$(cat "$RUN/openpolaris-pgphoto.pid" 2>/dev/null || true)" || return 1
    fi
    if [ -f "$TMP/child.pid" ]; then
        stop_test_process "$(cat "$TMP/child.pid" 2>/dev/null || true)" || return 1
    fi
    rm -f "$TMP/child.pid"
    rm -f "$RUN/openpolaris-pgphoto.pid" "$PROC/net/tcp"
    rm -rf "$PROC"/[0-9]*
}

# Even a failing regression must not leave the fake long-running pgphoto
# wrapper behind in the test host.
cleanup_all() {
    cleanup_launched || return 1
    rm -rf "$TMP"
}
finish() {
    status=$?
    trap - EXIT
    if ! cleanup_all; then
        exit 1
    fi
    exit "$status"
}
trap finish EXIT
trap 'exit 130' HUP INT TERM

# A 24-second init exceeds the old 20-second loop plus initial two seconds.
# The longer bounded readiness wait must allow it to finish.
OUT_SLOW=$TMP/slow.out
run_restart "$TMP/wrapper-slow" "$OUT_SLOW"
grep -q 'OK: port 8080 listening' "$OUT_SLOW"
cleanup_launched

# A process that never publishes readiness must still fail closed at the bound.
OUT_HUNG=$TMP/hung.out
STARTED=$(date +%s)
rc=0
TEST_WAIT_MAX=1 run_restart "$TMP/wrapper-hung" "$OUT_HUNG" || rc=$?
FINISHED=$(date +%s)
test "$rc" -ne 0
test "$((FINISHED - STARTED))" -lt 8
grep -q 'FAIL: pgphoto stayed alive but port 8080 did not become ready' "$OUT_HUNG"
cleanup_launched

# A process that dies after the initial check must not be marked successful
# when a different listener later appears. The original script was also run
# separately against this test to verify it detects the existing bug.
OUT_DEAD=$TMP/dead.out
rc=0
TEST_WAIT_MAX=5 run_restart "$TMP/wrapper-dies" "$OUT_DEAD" || rc=$?
test "$rc" -ne 0
grep -q 'FAIL: pgphoto exited during readiness wait' "$OUT_DEAD"
cleanup_launched

echo 'PASS: restart_gphoto waits for slow readiness but fails closed on hung startup (issue #253)'
