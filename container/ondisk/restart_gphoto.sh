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
# The restart lock is reclaimed when its owner is gone, for the same reason step 2
# reclaims the pgphoto launch lock. /var/run on this firmware is UBIFS root flash,
# NOT tmpfs (verified: `mount` lists only devtmpfs on /dev, and `df /var/run`
# reports ubi0:ubifs), so a lock directory left by a crash or a power cut survives
# a reboot. The K-3 III device carried one with an EMPTY pid file and an mtime of
# 2025-05-09, long predating the current boot, so every restart answered "another
# restart owns ...; refusing to race" and exited 1 -- across reboots, indefinitely.
# That made the USB supervisor's bounded rebind fail permanently and left it
# quarantining a healthy K-3 III for the whole boot (issue #297).
#
# BusyBox-safe: uses only /proc, kill, sleep, grep, tr, mv, readlink and awk.
# No pgrep/pkill.

RUN_DIR=${OPENPOLARIS_RUN_DIR:-/var/run}
PROC_ROOT=${OPENPOLARIS_PROC_ROOT:-/proc}
PIDFILE=$RUN_DIR/openpolaris-pgphoto.pid
LOCKDIR=$RUN_DIR/openpolaris-pgphoto.restart.lock
WRAPPER=${OPENPOLARIS_PGPHOTO_WRAPPER:-/app/bin/pgphoto}
STAGE2_BIN=${OPENPOLARIS_PGPHOTO_BINARY:-/app/lib/stage2/pgphoto.stage2ondisk}
LOG=${OPENPOLARIS_PGPHOTO_LOG:-/app/Clog.txt}
PORT_HEX=1F90   # 8080 in hex (for /proc/net/tcp grep)
WAIT_MAX=10     # seconds to wait for clean exit after TERM
# K-1 II camera discovery/configuration can take about 40 seconds while the
# process is alive and making progress. A 20-second limit caused the helper
# to report a false startup failure, after which the USB supervisor retried the
# rebind and made value-setting painfully slow. This remains a bounded
# readiness wait: the port must actually listen, and a hung process still
# fails closed. Keep an override for deterministic tests and future measured
# camera-specific tuning without changing the safe default.
START_WAIT_MAX=${OPENPOLARIS_PGPHOTO_START_WAIT_MAX:-90}

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
port_owned_by_pid() {
    # A different listener must not satisfy readiness. The old helper only
    # checked whether any process had bound 8080, which could report success
    # for a stale or foreign listener during a restart race. /proc/net/tcp and
    # /proc/net/tcp6 expose the socket inode; match that inode against the
    # expected pgphoto process's file descriptors.
    OWNER_PID=$1
    [ -d "$PROC_ROOT/$OWNER_PID/fd" ] || return 1
    for netfile in "$PROC_ROOT/net/tcp" "$PROC_ROOT/net/tcp6"; do
        [ -r "$netfile" ] || continue
        for inode in $(awk -v port=":$PORT_HEX" \
            '$2 ~ (port "$") && $4 == "0A" { print $10 }' \
            "$netfile" 2>/dev/null); do
            for fd in "$PROC_ROOT/$OWNER_PID/fd"/*; do
                [ -e "$fd" ] || [ -L "$fd" ] || continue
                link=$(readlink "$fd" 2>/dev/null || true)
                [ "$link" = "socket:[$inode]" ] && return 0
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

# --- helpers for lock ownership --------------------------------------------

read_pidfile() {
    # Print the pid in $1 only if it is a plausible numeric pid. Anything else --
    # empty, truncated by a power cut mid-write, or garbage -- prints nothing.
    p=$(cat "$1" 2>/dev/null)
    case "$p" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$p"
}

pid_is_restart_owner() {
    # True only if $1 is alive AND is a restart helper. A bare /proc/$pid existence
    # test is not enough: pid numbers are recycled, so a lock left over from an
    # earlier boot can name a pid the kernel has since handed to something else
    # entirely, and treating that as the owner would wedge the restart forever.
    [ -d "$PROC_ROOT/$1" ] || return 1
    CMD=$(tr '\0' '\n' < "$PROC_ROOT/$1/cmdline" 2>/dev/null | head -1)
    case "$CMD" in
        *restart_gphoto*) return 0 ;;
    esac
    return 1
}

# --- step 0: acquire restart lock (prevents watchdog race, issue #34) ------

if ! mkdir "$LOCKDIR" 2>/dev/null; then
    # The lock exists. It is only honoured if it has a live restart_gphoto owner.
    OWNER=$(read_pidfile "$LOCKDIR/pid" 2>/dev/null || true)
    if [ -n "$OWNER" ] && pid_is_restart_owner "$OWNER"; then
        echo "[restart_gphoto] restart lock owned by live restart_gphoto (PID $OWNER); refusing to race" >&2
        exit 1
    fi
    # No owner, an unreadable pid file, or a pid that is no longer this script.
    # Give a genuinely starting owner one second to publish its pid before
    # reclaiming, so this cannot steal the lock out from under a real restart.
    sleep 1
    OWNER=$(read_pidfile "$LOCKDIR/pid" 2>/dev/null || true)
    if [ -n "$OWNER" ] && pid_is_restart_owner "$OWNER"; then
        echo "[restart_gphoto] restart lock won by live restart_gphoto (PID $OWNER) during grace; refusing to race" >&2
        exit 1
    fi
    rm -rf "$LOCKDIR"
    if ! mkdir "$LOCKDIR" 2>/dev/null; then
        echo "[restart_gphoto] lost the race for $LOCKDIR; refusing to run twice" >&2
        exit 1
    fi
    # Say what was reclaimed: this exact condition once sat in /app/Clog.txt every
    # few seconds for a whole boot and read as a healthy device.
    echo "[restart_gphoto] reclaimed stale restart lock (owner ${OWNER:-none}, no live restart_gphoto)"
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

# Wait for the port to come up (MJPG-Streamer binds after camera/session init).
# This is a readiness condition, not a fixed sleep: return immediately when
# the listener appears, or fail closed when the bounded startup window expires.
i=0
while [ $i -lt "$START_WAIT_MAX" ]; do
    if [ ! -d "$PROC_ROOT/$NEWPID" ] || ! pid_is_pgphoto "$NEWPID"; then
        echo "[restart_gphoto] FAIL: expected pgphoto process exited or changed during readiness" >&2
        exit 1
    fi
    if port_owned_by_pid "$NEWPID"; then
        echo "[restart_gphoto] OK: pgphoto PID $NEWPID owns the port-8080 listener — restart successful"
        exit 0
    fi
    sleep 1
    i=$((i+1))
done

echo "[restart_gphoto] FAIL: pgphoto stayed alive but port 8080 did not become ready" >&2
exit 1
