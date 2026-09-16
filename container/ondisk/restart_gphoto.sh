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
}

# Issue #93: prove that a SPECIFIC PID owns the 8080 LISTEN socket, not just
# that *some* process has it.  Resolve the socket inode from /proc/net/tcp{,6}
# and check whether it appears under /proc/$PID/fd.
port_owned_by() {
    # $1 = PID to test.  Returns 0 only if that PID owns a LISTEN socket on 8080.
    # BusyBox-safe: no `local`, no pgrep/lsof — /proc + readlink + awk only.
    [ -n "$1" ] && [ -d "$PROC_ROOT/$1" ] || return 1
    inodes="" netfile=
    for netfile in "$PROC_ROOT/net/tcp" "$PROC_ROOT/net/tcp6"; do
        [ -r "$netfile" ] || continue
        # Extract inode (field 10) for LISTEN sockets on our port.
        inodes=$(awk -v port=":${PORT_HEX}" \
            '$2 ~ (port "$") && $4 == "0A" { print $10 }' "$netfile" 2>/dev/null)
        [ -n "$inodes" ] || continue
        for fd in "$PROC_ROOT/$1"/fd/*; do
            [ -L "$fd" ] || continue
            target=$(readlink "$fd" 2>/dev/null) || continue
            case "$target" in
                socket:\[*\]) ;;
                *) continue ;;
            esac
            # /proc/PID/fd/N -> socket:[INODE]
            inode=${target#socket:\[}; inode=${inode%\]}
            for want in $inodes; do
                [ "$inode" = "$want" ] && return 0
            done
        done
    done
    return 1
}

pid_is_pgphoto() {
    # Verify /proc/$1/cmdline contains "pgphoto" (matches both the wrapper
    # path /app/bin/pgphoto and the stage2 binary pgphoto.stage2ondisk).
    [ -d "$PROC_ROOT/$1" ] || return 1
    CMD=$(tr '\0' '\n' < "$PROC_ROOT/$1/cmdline" 2>/dev/null | head -1)
    [ "$CMD" = "$STAGE2_BIN" ]
}

pid_is_restart() {
    [ -n "$1" ] && [ -d "$PROC_ROOT/$1" ] || return 1
    CMD=$(tr '\0' '\n' < "$PROC_ROOT/$1/cmdline" 2>/dev/null)
    case "$CMD" in
        *restart_gphoto*) return 0 ;;
        *) return 1 ;;
    esac
}

# --- step 0: acquire restart lock (prevents watchdog race, issue #34) ------

if ! mkdir "$LOCKDIR" 2>/dev/null; then
    OWNER=$(cat "$LOCKDIR/pid" 2>/dev/null)
    case "$OWNER" in ''|*[!0-9]*) OWNER= ;; esac
    if pid_is_restart "$OWNER"; then
        echo "[restart_gphoto] another restart owns $LOCKDIR (PID $OWNER); refusing to race" >&2
        exit 1
    fi
    # SIGKILL/power loss, or later PID reuse, must not permanently disable the
    # only supported recovery path.
    rm -rf "$LOCKDIR"
    mkdir "$LOCKDIR" 2>/dev/null || {
        echo "[restart_gphoto] another restart won stale-lock recovery; refusing to race" >&2
        exit 1
    }
    echo "[restart_gphoto] reclaimed stale restart lock (owner ${OWNER:-unknown})"
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

# --- step 2b: reclaim a stale launch lock (issue #77) -----------------------
# A wrapper SIGKILLed or power-cycled mid-launch leaves the mkdir-based launch
# lock behind in persistent /var/run. The wrapper's own stale-lock reclaim only
# runs if it gets launched at all, so every later launch logs "another pgphoto
# launch is already in progress; refusing duplicate" and the watchdog restart
# becomes a permanent no-op (issue #77 candidate root cause 3). Reclaim the lock
# here, before launching: safe when the recorded owner is gone or no longer a
# pgphoto process. If the owner is alive AND is pgphoto, a launch is genuinely
# in progress — refuse to race it (the wrapper would do the same).
LAUNCH_LOCK="$RUN_DIR/openpolaris-pgphoto.launch.lock"
if [ -d "$LAUNCH_LOCK" ]; then
    LOCKPID=$(cat "$LAUNCH_LOCK/pid" 2>/dev/null)
    case "$LOCKPID" in ''|*[!0-9]*) LOCKPID= ;; esac
    if [ -n "$LOCKPID" ] && [ -d "$PROC_ROOT/$LOCKPID" ] && pid_is_pgphoto "$LOCKPID"; then
        echo "[restart_gphoto] launch lock owned by live pgphoto (PID $LOCKPID); refusing to race it" >&2
        exit 1
    fi
    # Owner gone, or a non-pgphoto leftover: give a just-created owner one
    # second to publish its PID, then reclaim.
    sleep 1
    LOCKPID=$(cat "$LAUNCH_LOCK/pid" 2>/dev/null)
    case "$LOCKPID" in ''|*[!0-9]*) LOCKPID= ;; esac
    if [ -n "$LOCKPID" ] && [ -d "$PROC_ROOT/$LOCKPID" ] && pid_is_pgphoto "$LOCKPID"; then
        echo "[restart_gphoto] launch lock won by live pgphoto (PID $LOCKPID) during grace; refusing to race it" >&2
        exit 1
    fi
    rm -rf "$LAUNCH_LOCK"
    echo "[restart_gphoto] reclaimed stale pgphoto launch lock (owner ${LOCKPID:-unknown})"
fi

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

# Wait for the port to come up AND prove the new pgphoto PID owns it.
# Issue #93: port_in_use() only proves *some* process has the listener;
# we must prove the expected pgphoto owner is alive and bound to 8080.
i=0
while [ $i -lt "$START_WAIT_MAX" ]; do
    if pid_is_pgphoto "$NEWPID" && port_owned_by "$NEWPID"; then
        echo "[restart_gphoto] OK: port 8080 listening — owned by pgphoto PID $NEWPID; restart successful"
        exit 0
    fi
    sleep 1
    i=$((i+1))
done

# Diagnostic fallback: distinguish "pgphoto dead" from "port not bound".
if ! pid_is_pgphoto "$NEWPID"; then
    echo "[restart_gphoto] FAIL: pgphoto (PID $NEWPID) exited before port 8080 was ready" >&2
else
    echo "[restart_gphoto] FAIL: pgphoto (PID $NEWPID) is alive but does not own port 8080 after ${START_WAIT_MAX}s" >&2
fi
exit 1
