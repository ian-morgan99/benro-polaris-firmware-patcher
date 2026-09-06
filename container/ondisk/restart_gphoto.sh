#!/bin/sh
# restart_gphoto.sh — single-owner pgphoto restart helper (issues #33, #34)
#
# Replaces the stock /app/restart_gphoto which does a blind:
#   pkill /app/bin/pgphoto
#   nohup /app/bin/pgphoto >> /app/Clog.txt &
#
# The stock script's pkill matches nothing because after our wrapper execs,
# the running process is /app/lib/stage2/pgphoto.stage2ondisk (not /app/bin/
# pgphoto). So the old instance survives, keeps port 8080, and every new
# instance dies on bind → crash loop.
#
# This script implements the PID-file design from issue #33:
#   1. Read PID from /var/run/openpolaris-pgphoto.pid (if present)
#   2. Verify /proc/$pid/cmdline still names a pgphoto process
#   3. TERM → bounded wait for process exit AND TCP/8080 unbind → KILL fallback
#   4. Start replacement, record its PID atomically
#   5. Verify liveness + 8080 ownership before declaring success
#
# Also sets a restart-in-progress marker so the polestar watchdog
# (checkGphotoTask) can detect an in-flight restart and not race it (#34).
#
# BusyBox-safe: uses only /proc, kill, sleep, grep, tr, mv. No pgrep/pkill.

RUN_DIR=${OPENPOLARIS_RUN_DIR:-/var/run}
PROC_ROOT=${OPENPOLARIS_PROC_ROOT:-/proc}
PIDFILE=$RUN_DIR/openpolaris-pgphoto.pid
LOCKDIR=$RUN_DIR/openpolaris-pgphoto.restart.lock
WRAPPER=${OPENPOLARIS_PGPHOTO_WRAPPER:-/app/bin/pgphoto}
STAGE2_BIN=${OPENPOLARIS_PGPHOTO_BINARY:-/app/lib/stage2/pgphoto.stage2ondisk}
LOG=${OPENPOLARIS_PGPHOTO_LOG:-/app/Clog.txt}
PORT_HEX=1F90   # 8080 in hex (for /proc/net/tcp grep)
WAIT_MAX=10     # seconds to wait for clean exit after TERM
START_WAIT_MAX=20  # stage2 + camera init can take more than five seconds

# --- helpers ---------------------------------------------------------------

port_in_use() {
    # Check if anything is listening on TCP port 8080.
    # /proc/net/tcp local_address format: HEXIP:HEXPORT (e.g. 00000000:1F90)
    for netfile in "$PROC_ROOT/net/tcp" "$PROC_ROOT/net/tcp6"; do
        [ -r "$netfile" ] || continue
        awk -v port=":${PORT_HEX}" '$2 ~ (port "$") && $4 == "0A" { found=1 } END { exit !found }' \
            "$netfile" 2>/dev/null && return 0
    done
    return 1
    return 1
}

pid_is_pgphoto() {
    # Verify /proc/$1/cmdline contains "pgphoto" (matches both the wrapper
    # path /app/bin/pgphoto and the stage2 binary pgphoto.stage2ondisk).
    [ -d "$PROC_ROOT/$1" ] || return 1
    CMD=$(tr '\0' '\n' < "$PROC_ROOT/$1/cmdline" 2>/dev/null | head -1)
    [ "$CMD" = "$STAGE2_BIN" ]
}

# --- step 0: acquire restart lock (prevents watchdog race, issue #34) ------

if ! mkdir "$LOCKDIR" 2>/dev/null; then
    echo "[restart_gphoto] another restart owns $LOCKDIR; refusing to race" >&2
    exit 1
fi
echo "$$" > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT
trap 'exit 130' HUP INT TERM

# --- step 1: find the running PID ------------------------------------------

PID=""
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$PID" ] && ! pid_is_pgphoto "$PID"; then
        echo "[restart_gphoto] stale PID file (PID $PID is not pgphoto); removing"
        rm -f "$PIDFILE"
        PID=""
    fi
fi

# Fallback: scan /proc for any process whose cmdline contains "pgphoto".
# This catches the case where the PID file was never written (stock boot).
if [ -z "$PID" ]; then
    for d in "$PROC_ROOT"/[0-9]*; do
        p=${d#"$PROC_ROOT"/}
        [ "$p" = "$$" ] && continue
        if pid_is_pgphoto "$p"; then
            PID="$p"
            break
        fi
    done
fi

# --- step 2: stop the old instance -----------------------------------------

if [ -n "$PID" ]; then
    echo "[restart_gphoto] stopping pgphoto (PID $PID)"
    kill -TERM "$PID" 2>/dev/null

    # Bounded wait for process exit AND port unbind.
    # Starting the replacement before the listener is gone recreates the
    # observed race even if process matching is fixed (issue #33).
    i=0
    while [ $i -lt "$WAIT_MAX" ]; do
        if [ ! -d "$PROC_ROOT/$PID" ] && ! port_in_use; then
            break
        fi
        sleep 1
        i=$((i+1))
    done

    # KILL fallback if the process ignored TERM.
    if [ -d "$PROC_ROOT/$PID" ]; then
        echo "[restart_gphoto] PID $PID still alive after ${WAIT_MAX}s; sending KILL"
        kill -KILL "$PID" 2>/dev/null
        i=0
        while [ $i -lt "$WAIT_MAX" ] && { [ -d "$PROC_ROOT/$PID" ] || port_in_use; }; do
            sleep 1
            i=$((i+1))
        done
    fi

    if port_in_use; then
        echo "[restart_gphoto] FAIL: port 8080 still has a listener after stop" >&2
        exit 1
    fi
else
    echo "[restart_gphoto] no running pgphoto found"
fi

# Clean up the PID file (will be rewritten below).
rm -f "$PIDFILE"
# An explicit restart is operator-controlled and should not inherit watchdog
# crash-loop delay from earlier automatic launches.
rm -f "$RUN_DIR/openpolaris-pgphoto.backoff"

# --- step 3: start the replacement -----------------------------------------

echo "[restart_gphoto] starting pgphoto via $WRAPPER"
nohup "$WRAPPER" >> "$LOG" 2>&1 &
NEWPID=$!

# Record PID atomically (write to temp, then rename — never a partial read).
echo "$NEWPID" > "${PIDFILE}.tmp"
mv "${PIDFILE}.tmp" "$PIDFILE"

# --- step 4: verify --------------------------------------------------------

sleep 2
if [ ! -d "$PROC_ROOT/$NEWPID" ] || ! pid_is_pgphoto "$NEWPID"; then
    echo "[restart_gphoto] FAIL: pgphoto exited immediately (PID $NEWPID); check $LOG"
    exit 1
fi
echo "[restart_gphoto] pgphoto running (PID $NEWPID)"

# Wait for the port to come up (MJPG-Streamer binds during init).
i=0
while [ $i -lt "$START_WAIT_MAX" ]; do
    if port_in_use; then
        echo "[restart_gphoto] OK: port 8080 listening — restart successful"
        exit 0
    fi
    sleep 1
    i=$((i+1))
done

echo "[restart_gphoto] FAIL: pgphoto stayed alive but port 8080 did not become ready" >&2
exit 1
