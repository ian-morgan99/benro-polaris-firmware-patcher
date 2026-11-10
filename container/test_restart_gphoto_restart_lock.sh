#!/bin/sh
# test_restart_gphoto_restart_lock.sh — issue #297
#
# The restart lock (step 0) must be reclaimed when its owner is gone, exactly as
# step 2 already reclaims the pgphoto launch lock. It was not: any existing lock
# directory produced "another restart owns ...; refusing to race" and exit 1.
#
# Why that matters more than it looks. /var/run on this firmware is UBIFS root
# flash, NOT tmpfs -- verified on the device: `mount` lists only devtmpfs on /dev
# and `df /var/run` reports ubi0:ubifs. So a lock left by a crash or a power cut
# survives a reboot. The K-3 III device carried one with an EMPTY pid file and an
# mtime of 2025-05-09, long predating the current boot. Every restart therefore
# refused, across reboots:
#
#   [restart_gphoto] another restart owns /var/run/openpolaris-pgphoto.restart.lock; refusing to race
#   [camera-usb] quarantined identity 1-1.2|25fb:0189|1:4 stable for 9 polls but bounded rebind failed; remaining degraded (issue #119)
#
# The camera enumerated correctly (25fb:0189 present in sysfs); the supervisor's
# bounded rebind could never succeed, so a healthy K-3 III was held quarantined
# for the entire boot and the WebUI published model:none. This is a functional
# regression caused by our own helper, not a model-table gap.
#
# Same mocking style as test_restart_gphoto_launch_lock.sh: fake /proc root, fake
# pgphoto wrapper that publishes its own proc entry and binds :8080.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RESTART=$ROOT/container/ondisk/restart_gphoto.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

PROC=$TMP/proc
RUN=$TMP/run
LOGF=$TMP/clog.txt
BIN=/app/lib/stage2/pgphoto.stage2ondisk
LOCK=$RUN/openpolaris-pgphoto.restart.lock

mkdir -p "$PROC/net" "$RUN"

cat > "$TMP/wrapper" <<'EOF'
#!/bin/sh
PR="$OPENPOLARIS_PROC_ROOT"
B="$OPENPOLARIS_PGPHOTO_BINARY"
mkdir -p "$PR/$$/fd"
printf '%s' "$B" > "$PR/$$/cmdline"
ln -s 'socket:[12345]' "$PR/$$/fd/3"
printf '  sl  local_address rem_address   st\n   0: 00000000:1F90 00000000:0000 0A 00000000:0000 00:00000000 00000000 1000 0 12345 1 0000000000000000 100 0 0 10 0\n' > "$PR/net/tcp"
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

# --- Case A: the exact condition found on the device -- lock dir, empty pid ---
# This is what was sitting on the device. It must be reclaimed, not honoured.
mkdir -p "$LOCK"
: > "$LOCK/pid"
OUTA=$TMP/caseA.out
rc=0
run_restart "$OUTA" || rc=$?
test "$rc" = "0" || { echo "FAIL case A: exit $rc"; cat "$OUTA"; exit 1; }
grep -q 'reclaimed stale restart lock' "$OUTA" || { echo "FAIL case A: no reclaim reported"; cat "$OUTA"; exit 1; }
test ! -e "$LOCK" || { echo "FAIL case A: lock still present after success"; exit 1; }
cleanup_launched

# --- Case B: lock owned by a LIVE restart_gphoto -> must NOT be reclaimed -----
# The guard has to keep working. Reclaiming unconditionally would let two restarts
# race, which is the whole reason step 0 exists (issue #34).
FAKEPID=999001
mkdir -p "$PROC/$FAKEPID"
printf '%s' "/app/restart_gphoto" > "$PROC/$FAKEPID/cmdline"
mkdir -p "$LOCK"
printf '%s\n' "$FAKEPID" > "$LOCK/pid"
OUTB=$TMP/caseB.out
rc=0
run_restart "$OUTB" || rc=$?
test "$rc" != "0" || { echo "FAIL case B: ran while a live owner held the lock"; exit 1; }
grep -q 'refusing to race' "$OUTB" || { echo "FAIL case B: did not refuse"; cat "$OUTB"; exit 1; }
! grep -q 'reclaimed stale restart lock' "$OUTB" || { echo "FAIL case B: stole a live lock"; exit 1; }
test -e "$LOCK/pid" || { echo "FAIL case B: removed a live owner's lock"; exit 1; }
rm -rf "$PROC/$FAKEPID" "$LOCK"

# --- Case C: pid recycled to an unrelated process -> stale, reclaim ----------
# A lock from an earlier boot can name a pid the kernel has since reassigned.
# Existence alone must not count as ownership.
FAKEPID=999002
mkdir -p "$PROC/$FAKEPID"
printf '%s' "/usr/sbin/ntpd" > "$PROC/$FAKEPID/cmdline"
mkdir -p "$LOCK"
printf '%s\n' "$FAKEPID" > "$LOCK/pid"
OUTC=$TMP/caseC.out
rc=0
run_restart "$OUTC" || rc=$?
test "$rc" = "0" || { echo "FAIL case C: exit $rc"; cat "$OUTC"; exit 1; }
grep -q 'reclaimed stale restart lock' "$OUTC" || { echo "FAIL case C: recycled pid treated as owner"; cat "$OUTC"; exit 1; }
cleanup_launched

# --- Case D: no lock present -> normal restart, no reclaim line ---------------
OUTD=$TMP/caseD.out
rc=0
run_restart "$OUTD" || rc=$?
test "$rc" = "0" || { echo "FAIL case D: exit $rc"; cat "$OUTD"; exit 1; }
! grep -q 'reclaimed stale restart lock' "$OUTD" || { echo "FAIL case D: reclaimed nothing"; exit 1; }
cleanup_launched

echo 'PASS: restart_gphoto reclaims a stale restart lock, honours a live owner, and survives pid recycling (issue #297)'
