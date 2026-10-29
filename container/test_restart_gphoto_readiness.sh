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
    sleep 3
    printf '  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A\n' > "$PR/net/tcp"
) &
trap 'rm -f "$PR/net/tcp"; rm -rf "$PR/$$"; exit 0' TERM INT
while :; do sleep 0.2; done
EOF

cat > "$TMP/wrapper-hung" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
mkdir -p "$PR/$$"
printf '%s' "$BIN" > "$PR/$$/cmdline"
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
    OPENPOLARIS_PGPHOTO_START_WAIT_MAX=5 \
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

# A slow init publishes readiness after three seconds, inside the five-second
# test window. The helper must wait for the real listener and succeed.
OUT_SLOW=$TMP/slow.out
run_restart "$TMP/wrapper-slow" "$OUT_SLOW"
grep -q 'OK: port 8080 listening' "$OUT_SLOW"
cleanup_launched

# A process that never publishes readiness must still fail closed at the bound.
OUT_HUNG=$TMP/hung.out
rc=0
run_restart "$TMP/wrapper-hung" "$OUT_HUNG" || rc=$?
test "$rc" -ne 0
grep -q 'FAIL: pgphoto stayed alive but port 8080 did not become ready' "$OUT_HUNG"
cleanup_launched

echo 'PASS: restart_gphoto waits for slow readiness but fails closed on hung startup (issue #253)'
