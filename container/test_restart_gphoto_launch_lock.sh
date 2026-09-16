#!/bin/sh
# test_restart_gphoto_launch_lock.sh — issue #77
#
# Verifies the restart helper reclaims a STALE pgphoto launch lock (left behind
# when a wrapper is SIGKILLed or power-cycled mid-launch) instead of letting it
# wedge every later launch with "another pgphoto launch is already in progress".
# Also confirms a run with no launch lock present still succeeds (no reclaim).
#
# Mirrors the mocking style of test_pgphoto_wrapper_lock.sh: a fake /proc root,
# a fake pgphoto wrapper that publishes its own proc entry, and a pre-seeded
# net/tcp so the port-readiness wait returns immediately.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RESTART=$ROOT/container/ondisk/restart_gphoto.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

PROC=$TMP/proc
RUN=$TMP/run
LOGF=$TMP/clog.txt
BIN=/app/lib/stage2/pgphoto.stage2ondisk

# --- fake /proc root --------------------------------------------------------
mkdir -p "$PROC/net" "$RUN"

# --- fake pgphoto wrapper ---------------------------------------------------
# Publishes its own /proc entry (cmdline == the stage2 binary) so pid_is_pgphoto
# accepts it, simulates MJPG-Streamer binding :8080 by writing a LISTEN-state
# (0A) entry to the fake /proc/net/tcp AND a matching socket fd symlink under
# /proc/$$/fd so port_owned_by() can resolve the inode match.  Tears both down
# on TERM.  $$ is the PID restart_gphoto records as NEWPID.
cat > "$TMP/wrapper" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
BIN="$OPENPOLARIS_PGPHOTO_BINARY"
mkdir -p "$PR/$$/fd"
printf '%s' "$BIN" > "$PR/$$/cmdline"
# Simulate MJPG-Streamer binding :1F90 (8080) during init.
# The net/tcp entry carries inode 42 in field 10 (the real /proc/net/tcp
# layout: sl local rem st tx:rx tr:tm retrnsmt uid timeout inode); the
# matching fd symlink lets port_owned_by() resolve the inode match under
# /proc/$PID/fd.
printf '  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 42\n' > "$PR/net/tcp"
ln -s "socket:[42]" "$PR/$$/fd/3"
trap 'rm -f "$PR/net/tcp"; rm -rf "$PR/$$"; exit 0' TERM
while :; do sleep 0.3 & wait $!; done
EOF
chmod +x "$TMP/wrapper"

run_restart() {
    OPENPOLARIS_RUN_DIR="$RUN" \
    OPENPOLARIS_PROC_ROOT="$PROC" \
    OPENPOLARIS_PGPHOTO_WRAPPER="$TMP/wrapper" \
    OPENPOLARIS_PGPHOTO_BINARY="$BIN" \
    OPENPOLARIS_PGPHOTO_LOG="$LOGF" \
    sh "$RESTART" > "$1" 2>&1
}

# Kill whatever the last run launched (recorded in the PID file) and wait for
# it to actually die, so the next case starts from a clean port-8080 state.
cleanup_launched() {
    if [ -f "$RUN/openpolaris-pgphoto.pid" ]; then
        LP=$(cat "$RUN/openpolaris-pgphoto.pid" 2>/dev/null || true)
        case "$LP" in ''|*[!0-9]*) LP= ;; esac
        if [ -n "$LP" ]; then
            kill "$LP" 2>/dev/null || :
            i=0
            while [ $i -lt 10 ] && kill -0 "$LP" 2>/dev/null; do
                sleep 0.2
                i=$((i+1))
            done
        fi
    fi
    rm -f "$RUN/openpolaris-pgphoto.pid"
}

# --- Case A: stale launch lock (dead owner) is reclaimed --------------------
# Seed a stale restart lock too. The restart path must recover from its own
# prior SIGKILL/power-loss residue before it can repair pgphoto.
mkdir -p "$RUN/openpolaris-pgphoto.restart.lock"
echo 888888 > "$RUN/openpolaris-pgphoto.restart.lock/pid"
mkdir -p "$RUN/openpolaris-pgphoto.launch.lock"
echo 999999 > "$RUN/openpolaris-pgphoto.launch.lock/pid"   # dead, not in fake /proc

OUTA=$TMP/caseA.out
rc=0
run_restart "$OUTA" || rc=$?
test "$rc" = "0"
printf '%s\n' "$(cat "$OUTA")" | grep -q 'reclaimed stale pgphoto launch lock'
printf '%s\n' "$(cat "$OUTA")" | grep -q 'reclaimed stale restart lock'
# The stale lock must be gone after a successful restart.
test ! -e "$RUN/openpolaris-pgphoto.launch.lock"
cleanup_launched

# --- Case B: no launch lock present -> normal restart, no reclaim -----------
OUTB=$TMP/caseB.out
rc=0
run_restart "$OUTB" || rc=$?
test "$rc" = "0"
! printf '%s\n' "$(cat "$OUTB")" | grep -q 'reclaimed stale pgphoto launch lock'
cleanup_launched

# --- Case C: live unrelated PID reuse does not own the restart lock ---------
mkdir -p "$RUN/openpolaris-pgphoto.restart.lock" "$PROC/4242"
echo 4242 > "$RUN/openpolaris-pgphoto.restart.lock/pid"
printf '%s\0' /bin/unrelated > "$PROC/4242/cmdline"
OUTC=$TMP/caseC.out
rc=0
run_restart "$OUTC" || rc=$?
test "$rc" = "0"
printf '%s\n' "$(cat "$OUTC")" | grep -q 'reclaimed stale restart lock'
cleanup_launched

# --- Case D: genuine concurrent restart remains fail-closed ----------------
mkdir -p "$RUN/openpolaris-pgphoto.restart.lock" "$PROC/4343"
echo 4343 > "$RUN/openpolaris-pgphoto.restart.lock/pid"
printf '%s\0%s\0' /bin/sh /app/restart_gphoto > "$PROC/4343/cmdline"
OUTD=$TMP/caseD.out
rc=0
run_restart "$OUTD" || rc=$?
test "$rc" = "1"
grep -q 'another restart owns' "$OUTD"
rm -rf "$RUN/openpolaris-pgphoto.restart.lock" "$PROC/4343"

echo 'PASS: restart_gphoto validates restart/launch lock ownership and restarts cleanly (issue #77)'
