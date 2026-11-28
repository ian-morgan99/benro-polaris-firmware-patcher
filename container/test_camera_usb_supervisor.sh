#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SUPERVISOR=$ROOT/container/ondisk/camera_usb_supervisor.sh
TMP=$(mktemp -d)
mkdir -p "$TMP/sys" "$TMP/run" "$TMP/proc"

# Diagnostics for unexpected aborts. The suite runs under `set -eu`, and dash has
# no ERR trap, so any command that fails outside an explicit `|| { echo FAIL; exit 1; }`
# exits with no message at all. CI run 46086618810 showed exactly that: the gate
# reported "FAIL: camera USB supervisor behaviour" with a completely empty log, so
# nothing could be learned from it.
#
# xtrace therefore goes to a side file on stderr, and the EXIT trap dumps its tail
# to the real stderr (kept on fd 4) whenever the status is non-zero. FAIL messages
# in this suite are plain `echo`, i.e. stdout, so they still reach the gate log
# directly and are unaffected by the redirect.
TRACE=$TMP/xtrace
exec 4>&2
exec 2>"$TRACE"
set -x

trap 'st=$?
      if [ "$st" -ne 0 ]; then
          printf "%s\n" "--- suite aborted with status $st; last 60 xtrace lines follow ---" >&4
          tail -n 60 "$TRACE" >&4 2>/dev/null || printf "%s\n" "no trace captured" >&4
      fi
      rm -rf "$TMP"' EXIT HUP INT TERM

make_usb() {
    # Device construction must be atomic in two distinct ways.
    #
    # (1) A device must never appear half-built. fingerprint() globs $TMP/sys on
    #     every poll and only skips a device whose idVendor/idProduct are unreadable,
    #     so an *empty but existing* file yields an identity like "1-2|25fb:|:". That
    #     was observed under load as "awaiting reconnection of 1-2|25fb:|:" plus
    #     spurious restarts, making the cycle test report 5 restarts where it asserts
    #     exactly 4. Each attribute is therefore written to a temp file and renamed
    #     into place, so every file is always either absent or complete.
    #
    # (2) A device must never transiently vanish when only its devnum changes. The
    #     obvious fix -- build elsewhere and rename the directory into place -- does
    #     that, because rename() cannot replace a non-empty directory: the old one has
    #     to be removed first, and in that window fingerprint() sees no camera at all.
    #     That produced an extra absent->present restart, so the grace-reconnect test
    #     reported 2 restarts where it asserts exactly 1. When the directory already
    #     exists its attributes are replaced in place instead, keeping the device
    #     continuously present with a complete identity throughout.
    _dir=$TMP/sys/$1
    mkdir -p "$TMP/sys"
    if [ ! -d "$_dir" ]; then
        _stage=$TMP/.build/$1
        rm -rf "$_stage"
        mkdir -p "$_stage/power"
        printf '%s\n' "$2" > "$_stage/idVendor"
        printf '%s\n' "$3" > "$_stage/idProduct"
        printf '%s\n' "$4" > "$_stage/busnum"
        printf '%s\n' "$5" > "$_stage/devnum"
        printf 'auto\n' > "$_stage/power/control"
        # mv onto an existing directory would nest instead of replacing, leaving
        # $TMP/sys/<dev> with no attributes at its top level -- fingerprint() then
        # skips it and the supervisor sees the camera vanish. Remove any stale
        # target first (atomic enough: this branch only runs when it is absent).
        [ -d "$_dir" ] && rm -rf "$_dir"
        mv "$_stage" "$_dir"
        return 0
    fi
    mkdir -p "$_dir/power"
    for _a in idVendor idProduct busnum devnum; do
        case "$_a" in
            idVendor)  _v=$2 ;;
            idProduct) _v=$3 ;;
            busnum)    _v=$4 ;;
            devnum)    _v=$5 ;;
        esac
        printf '%s\n' "$_v" > "$_dir/.$_a.tmp"
        mv -f "$_dir/.$_a.tmp" "$_dir/$_a"
    done
    [ -f "$_dir/power/control" ] || printf 'auto\n' > "$_dir/power/control"
}


remove_usb() {
    # Unplug must be atomic too. `rm -rf $TMP/sys/<dev>` deletes the attribute
    # files one at a time, so a poll landing mid-deletion sees a device that still
    # has idVendor/idProduct but has already lost busnum/devnum -- fingerprint()
    # guards only the first two, so it returns an identity like "1-2|25fb:0183|:".
    # That was seen under load as a spurious "stable identity change:
    # 1-2|25fb:0183|1:3 -> 1-2|25fb:0183|:" plus an extra restart, which made the
    # cycle test report 5 restarts where it asserts exactly 4. rename() is atomic
    # within a filesystem, so the device either exists complete or not at all; the
    # actual unlinking happens afterwards on a directory no poll can see.
    [ -d "$TMP/sys/$1" ] || return 0
    mkdir -p "$TMP/.trash"
    # $$ is constant for the whole suite, so a fixed name collides across calls:
    # the second mv would move the device *inside* the first trash directory
    # instead of renaming onto it. mktemp gives a unique, empty target.
    _gone=$(mktemp -d "$TMP/.trash/$1.XXXXXX") || { rm -rf "$TMP/sys/$1"; return 0; }
    rmdir "$_gone"
    if mv "$TMP/sys/$1" "$_gone" 2>/dev/null; then
        rm -rf "$_gone"
    else
        rm -rf "$TMP/sys/$1"
    fi
}

RESTART_LOG=$TMP/restarts
export RESTART_LOG
cat > "$TMP/restart" <<'EOF'
#!/bin/sh
printf 'restart\n' >> "$RESTART_LOG"
EOF
chmod +x "$TMP/restart"

# --- shared wait helpers (defined up front so every test can use them) ---
count_matches() {
    # grep -c exits 1 when nothing matched, so `... || echo 0` emits a second
    # line and yields "0\n0", which makes [ -ge ] fail with "Illegal number".
    _n=$(grep -c "$2" "$1" 2>/dev/null | head -1) || _n=""
    printf '%s\n' "${_n:-0}"
}

wait_for_log() {
    _f=$1; _pat=$2; _i=0
    while [ "$_i" -lt "${WAIT_BUDGET:-400}" ]; do
        grep -q "$_pat" "$_f" 2>/dev/null && return 0
        sleep 0.05; _i=$((_i + 1))
    done
    return 1
}

wait_for_count() {
    # Occurrence-counted wait. wait_for_log only answers "has this line EVER
    # appeared", so reusing it per cycle returns instantly from the first
    # iteration onward and a multi-cycle test would assert nothing. Budget is
    # overridable because some tests drive several full poll cycles.
    _f=$1; _pat=$2; _want=$3; _i=0
    _max=${4:-${WAIT_BUDGET:-400}}
    while [ "$_i" -lt "$_max" ]; do
        [ "$(count_matches "$_f" "$_pat")" -ge "$_want" ] && return 0
        sleep 0.05; _i=$((_i + 1))
    done
    return 1
}


# Stable camera identity: no restart. An unrelated hub is ignored.
make_usb 1-1 1a40 0101 1 2
make_usb 1-2 25fb 0183 1 3
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_MAX_POLLS=3 sh "$SUPERVISOR" > "$TMP/stable.out"
test ! -e "$RESTART_LOG"

# A one-poll transient is debounced; a stable device-address/body change causes
# exactly one restart, then becomes the new baseline instead of looping.
# STARTUP_GRACE_POLLS=0: this test exercises post-startup debounce/restart, so
# disable the #121 startup grace window to preserve the original semantics.
rm -rf "$TMP/run/openpolaris-camera-usb-supervisor.lock"
: > "$TMP/change.out"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.1 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_MAX_POLLS=8 sh "$SUPERVISOR" > "$TMP/change.out" &
pid=$!
sleep 0.15
printf '4\n' > "$TMP/sys/1-2/devnum"
wait "$pid"
test "$(wc -l < "$RESTART_LOG")" -eq 1
grep -q 'stable identity change' "$TMP/change.out"

# If another owner holds the restart_gphoto lock during a camera re-enumeration,
# the supervisor must retain the stale baseline and retry once the lock clears.
# It must not accept the new identity merely because the first helper call lost
# the race (the exact failure observed in the 2026-09-29 Polaris Clog).
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0189 1 3
RETRY_LOG=$TMP/retry-attempts
export RETRY_LOG
cat > "$TMP/restart-once-busy" <<'EOF'
#!/bin/sh
n=0
[ ! -r "$RETRY_LOG" ] || n=$(cat "$RETRY_LOG")
n=$((n + 1))
printf '%s\n' "$n" > "$RETRY_LOG"
[ "$n" -ge 2 ]
EOF
chmod +x "$TMP/restart-once-busy"
: > "$TMP/retry.out"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart-once-busy OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 OPENPOLARIS_USB_STABLE_POLLS=2 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=2 OPENPOLARIS_USB_RESTART_RETRY_POLLS=3 \
OPENPOLARIS_USB_MAX_POLLS=18 sh "$SUPERVISOR" > "$TMP/retry.out" 2>&1 &
pid=$!
sleep 0.15
printf '4\n' > "$TMP/sys/1-1/devnum"
wait "$pid"
test "$(cat "$RETRY_LOG")" = 2
grep -q 'identity remains pending' "$TMP/retry.out"
grep -q 'pgphoto restart complete (restart 2/' "$TMP/retry.out"
! grep -q 'identity accepted to prevent a loop' "$TMP/retry.out"

# A stale lock whose PID was reused by an unrelated live process must be
# reclaimed; existence alone is not ownership.
rm -rf "$TMP/run/openpolaris-camera-usb-supervisor.lock"
mkdir -p "$TMP/run/openpolaris-camera-usb-supervisor.lock" "$TMP/proc/4242"
echo 4242 > "$TMP/run/openpolaris-camera-usb-supervisor.lock/pid"
printf '%s\0' /bin/unrelated > "$TMP/proc/4242/cmdline"
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.01 \
OPENPOLARIS_USB_MAX_POLLS=1 sh "$SUPERVISOR" > "$TMP/pid-reuse.out"
grep -q 'supervisor ready' "$TMP/pid-reuse.out"

# A genuine shell-script owner has the interpreter as argv[0] and the script as
# a later argument; preserve that lock and do not start a second supervisor.
rm -rf "$TMP/run/openpolaris-camera-usb-supervisor.lock"
mkdir -p "$TMP/run/openpolaris-camera-usb-supervisor.lock" "$TMP/proc/4343"
echo 4343 > "$TMP/run/openpolaris-camera-usb-supervisor.lock/pid"
printf '%s\0%s\0' /bin/sh /app/lib/stage2/camera_usb_supervisor.sh > "$TMP/proc/4343/cmdline"
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc OPENPOLARIS_USB_MAX_POLLS=1 \
sh "$SUPERVISOR" > "$TMP/genuine-owner.out"
test ! -s "$TMP/genuine-owner.out"
test "$(cat "$TMP/run/openpolaris-camera-usb-supervisor.lock/pid")" = "4343"

# Issue #121: startup-order crash. A camera that is already powered on at app
# launch can re-enumerate (device-number change) while Benro Connect is still
# initialising; a restart there races the initial session open and crashes it.
# The supervisor must absorb identity changes during the bounded startup grace
# window (no restart), then resume normal debounce/restart logic afterwards.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3   # camera already present at supervisor start
# Polls 1-3 (grace window, default 3): the device re-enumerates to a new
# devnum on poll 2 — a transient startup flap that must NOT restart pgphoto.
(
    sleep 0.05
    remove_usb 1-1
    make_usb 1-1 25fb 0183 1 7   # same body, new device number (re-enumeration)
) &
FLAP_PID=$!
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_MAX_POLLS=3 sh "$SUPERVISOR" > "$TMP/grace.out"
wait "$FLAP_PID" 2>/dev/null || true
test ! -e "$RESTART_LOG"   # no restart during the startup grace window

# After the grace window, a stable identity change still causes exactly one
# restart (the normal #57 behaviour is preserved).
#
# This was originally driven by `sleep 0.2` to land the change "past the 3-poll
# (0.15s) grace window". That is unsound: the window is measured in POLLS, not
# wall-clock time, and each poll costs at least POLL_SECS plus the work of
# fingerprint() and camera-state probing. Under CI load a poll takes longer than
# 0.05 s, so 0.2 s lands inside the window, the change is absorbed into the
# baseline, and no restart ever fires -- which is how this test failed
# intermittently in CI (run 46091054438, `test 0 = 1`). It now waits for the
# supervisor's own "window closed" marker before mutating, so the ordering is
# guaranteed rather than guessed.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
POST_GRACE_LOG=$TMP/post-grace.out
: > "$POST_GRACE_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STABLE_POLLS=1 OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 \
OPENPOLARIS_USB_MAX_POLLS=0 sh "$SUPERVISOR" >"$POST_GRACE_LOG" 2>&1 &
pg_pid=$!
wait_for_log "$POST_GRACE_LOG" 'supervisor ready' || {
    kill "$pg_pid" 2>/dev/null || true; wait "$pg_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined for the post-grace test (#121)"; exit 1
}
wait_for_log "$POST_GRACE_LOG" 'startup grace: window closed' || {
    kill "$pg_pid" 2>/dev/null || true; wait "$pg_pid" 2>/dev/null || true
    echo "FAIL: startup grace window never closed (#121)"
    cat "$POST_GRACE_LOG"; exit 1
}
# The window is provably shut and the baseline is still devnum 3, so this change
# is a genuine post-startup one.
remove_usb 1-1
make_usb 1-1 25fb 0183 1 9   # genuine body/device change after startup
wait_for_count "$RESTART_LOG" 'restart' 1 || {
    kill "$pg_pid" 2>/dev/null || true; wait "$pg_pid" 2>/dev/null || true
    echo "FAIL: no restart for a stable identity change after the grace window (#121)"
    cat "$POST_GRACE_LOG"; exit 1
}
sleep 0.3
kill "$pg_pid" 2>/dev/null || true; wait "$pg_pid" 2>/dev/null || true
test "$(count_matches "$RESTART_LOG" restart)" -eq 1 || {
    echo "FAIL: post-grace identity change cost $(count_matches "$RESTART_LOG" restart) restarts, expected 1 (#121)"
    cat "$POST_GRACE_LOG"; exit 1
}

# Issue #121 (TA follow-up): a GENUINE camera disconnect/reconnect during the
# startup grace window. The grace window absorbs EVERY fingerprint change, not
# just same-body devnum churn -- so a real removal in that interval is ignored and
# becomes the new baseline. Once the window closes, the reconnected (different)
# identity is a genuine change from what pgphoto originally bound to, so the normal
# debounce logic must fire exactly one restart to rebind it. A same-body reconnect
# that lands on the original identity would correctly need no restart; this case
# pins that the supervisor does not silently keep pgphoto on stale camera/session
# state after a grace-window reconnect.
#
# Same wall-clock-vs-polls bug as above, and worse: it chained two `sleep 0.1`
# calls to place the disconnect at "~poll 2" and the reconnect at "~poll 4". Both
# are guesses about poll timing. Here the disconnect is observed by waiting for the
# absorb line itself, and the reconnect waits for the window-closed marker, so each
# phase is synchronised on an event the supervisor actually emitted.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3   # camera present at supervisor start (baseline devnum 3)
GRACE_RECONNECT_LOG=$TMP/grace-reconnect.out
: > "$GRACE_RECONNECT_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STABLE_POLLS=1 OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 \
OPENPOLARIS_USB_MAX_POLLS=0 sh "$SUPERVISOR" >"$GRACE_RECONNECT_LOG" 2>&1 &
gr_pid=$!
wait_for_log "$GRACE_RECONNECT_LOG" 'supervisor ready' || {
    kill "$gr_pid" 2>/dev/null || true; wait "$gr_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined for the grace-reconnect test (#121)"; exit 1
}
# Disconnect while the window is still open. The absorb line is the proof that it
# was seen inside the window, so no sleep is needed and none is used.
remove_usb 1-1
wait_for_log "$GRACE_RECONNECT_LOG" 'startup grace: absorbing identity change' || {
    kill "$gr_pid" 2>/dev/null || true; wait "$gr_pid" 2>/dev/null || true
    echo "FAIL: disconnect during the grace window was not absorbed (#121)"
    cat "$GRACE_RECONNECT_LOG"; exit 1
}
test ! -e "$RESTART_LOG" || {
    echo "FAIL: restart fired while the grace window was still open (#121)"; exit 1
}
# Reconnect only once the window has provably closed, to a DIFFERENT devnum.
wait_for_log "$GRACE_RECONNECT_LOG" 'startup grace: window closed' || {
    kill "$gr_pid" 2>/dev/null || true; wait "$gr_pid" 2>/dev/null || true
    echo "FAIL: startup grace window never closed in the reconnect test (#121)"
    cat "$GRACE_RECONNECT_LOG"; exit 1
}
make_usb 1-1 25fb 0183 1 9   # reconnect to a DIFFERENT devnum after the window
wait_for_count "$RESTART_LOG" 'restart' 1 || {
    kill "$gr_pid" 2>/dev/null || true; wait "$gr_pid" 2>/dev/null || true
    echo "FAIL: reconnected identity did not trigger exactly one restart (#121)"
    cat "$GRACE_RECONNECT_LOG"; exit 1
}
sleep 0.3
kill "$gr_pid" 2>/dev/null || true; wait "$gr_pid" 2>/dev/null || true
test "$(count_matches "$RESTART_LOG" restart)" -eq 1 || {
    echo "FAIL: grace-window reconnect cost $(count_matches "$RESTART_LOG" restart) restarts, expected 1 (#121)"
    cat "$GRACE_RECONNECT_LOG"; exit 1
}
grep -q "startup grace: absorbing identity change" "$GRACE_RECONNECT_LOG"

# Issue #119: live-view churn / USB disappearance. A fast re-enumeration flap
# (device-number keeps changing while previewing) must not restart pgphoto on
# every poll -- that is the dlopen + 64-shim churn that drains the battery and
# drops the camera off USB. The bounded restart budget caps the total restarts;
# once exhausted the supervisor accepts the current identity and stops re-dlopening.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
# Identities 4 and 5 each persist for ~24 polls (1.2 s at 0.05 s/poll), well
# above COOLDOWN=4, so each fires a restart. Identity 6 then persists for ~10
# polls (0.5 s), enough to reach the stable-identity threshold and trigger the
# quarantine (budget exhausted, churn suppressed). After that the identity flaps
# faster (0.1 s = 2 polls < COOLDOWN=4) so no quarantined identity ever stays
# stable long enough to revalidate -- which would reset the budget and allow a
# 3rd restart. The supervisor therefore stays quarantined for the rest of the
# window: dlopen loop ends instead of running for the whole window.
(
    sleep 1.2; remove_usb 1-1; make_usb 1-1 25fb 0183 1 4   # restart #1 (~t=1.4)
    sleep 1.2; remove_usb 1-1; make_usb 1-1 25fb 0183 1 5   # restart #2 (~t=2.6), budget exhausted
    sleep 1.2; remove_usb 1-1; make_usb 1-1 25fb 0183 1 6   # quarantine (~t=4.2)
    sleep 0.8   # hold identity 6 stable for ~16 polls (>> COOLDOWN=4): the quarantine triggers AND the rebind-on-revalidation fires deterministically (restart #3)
    n=7
    while :; do
        sleep 0.1
        remove_usb 1-1
        make_usb 1-1 25fb 0183 1 "$n"
        n=$((n + 1))
    done
) &
FLAP2=$!
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=4 \
OPENPOLARIS_USB_MAX_RESTARTS=2 OPENPOLARIS_USB_MAX_POLLS=200 \
sh "$SUPERVISOR" > "$TMP/churn.out" 2>&1
kill "$FLAP2" 2>/dev/null; wait "$FLAP2" 2>/dev/null || true
# The restart budget (2) caps the churn restarts even though the identity kept
# changing -- the dlopen loop ends instead of running for the whole window.
# Issue #119 (TA follow-up): identity 6 holds for ~10 polls (>= COOLDOWN) before
# the flap begins, so the quarantine-exit rebind fires one additional restart
# (#3) on that stable window; the subsequent identity-7+ flap stays suppressed.
# Total: #1, #2 (churn within budget) + #3 (rebind on revalidation).
test "$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0)" = "3"
grep -q 'restart_budget_exhausted' "$TMP/churn.out"

# Issue #119 (TA release-safety follow-up): after the final allowed restart, an
# identity change must NOT be treated as a healthy session. The supervisor enters
# an explicit quarantine (churn suppressed, `restart_budget_exhausted` logged)
# and only resumes normal operation after a positive stable-identity condition
# revalidates the quarantined identity. Here the identity keeps changing while
# quarantined, so no further restarts fire for the rest of the window.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
(
    # Identities 4 and 5 each persist for ~24 polls (1.2 s at 0.05 s/poll), well
    # above COOLDOWN=4, so each fires a restart. Identity 6 then persists for
    # ~10 polls (0.5 s), enough to reach the stable-identity threshold and
    # trigger the quarantine (budget exhausted, churn suppressed). After that
    # the identity flaps faster (0.1 s = 2 polls < COOLDOWN=4) so no quarantined
    # identity ever stays stable long enough to revalidate -- which would reset
    # the budget and allow a 3rd restart. The supervisor therefore stays
    # quarantined for the rest of the window.
    sleep 1.2; remove_usb 1-1; make_usb 1-1 25fb 0183 1 4   # restart #1 (~t=1.4)
    sleep 1.2; remove_usb 1-1; make_usb 1-1 25fb 0183 1 5   # restart #2 (~t=2.6), budget exhausted
    sleep 1.2; remove_usb 1-1; make_usb 1-1 25fb 0183 1 6   # quarantine (~t=4.2)
    sleep 0.3   # hold identity 6 for ~6 polls: enough for the main loop to quarantine (stable>=COOLDOWN=4) but, with REBIND_STABLE_POLLS=20, qstable never reaches the rebind threshold before the flap resets it -- so no 3rd restart fires
    n=7
    while :; do
        sleep 0.1
        remove_usb 1-1
        make_usb 1-1 25fb 0183 1 "$n"
        n=$((n + 1))
    done
) &
POST_PID=$!
# REBIND_STABLE_POLLS=20 decouples the rebind threshold from the main-loop
# quarantine trigger (COOLDOWN=4): identity 6 quarantines after 4 stable polls,
# but the rebind-on-revalidation would need 20 consecutive stable polls -- far
# longer than the ~6-poll hold -- so it never fires and the test stays at 2 restarts.
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=4 \
OPENPOLARIS_USB_REBIND_STABLE_POLLS=20 \
OPENPOLARIS_USB_MAX_RESTARTS=2 OPENPOLARIS_USB_MAX_POLLS=200 \
sh "$SUPERVISOR" > "$TMP/quarantine.out" 2>&1
kill "$POST_PID" 2>/dev/null; wait "$POST_PID" 2>/dev/null || true
# Exactly the budgeted 2 restarts. Every post-budget identity change is
# quarantined (churn suppressed, `restart_budget_exhausted` logged) and never
# revalidates because the identity keeps changing faster than the cooldown --
# so it is not silently accepted as a healthy session. No 3rd restart fires.
test "$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0)" = "2"
grep -q 'restart_budget_exhausted' "$TMP/quarantine.out"

# Issue #119 (TA release-safety follow-up): the quarantined identity resumes
# normal operation only after a positive stable-identity condition revalidates it
# (unchanged for COOLDOWN consecutive polls). Revalidation resets the restart
# budget, so a later genuine identity change restarts pgphoto again.
# Issue #119 (TA follow-up): leaving the quarantine now requires a bounded
# rebind (a successful restart-helper run) in addition to identity stability, so
# the revalidation fires its own restart (#3) before normal operation resumes and
# the later genuine change fires #4.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
(
    sleep 0.5;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 4   # restart #1 (~0.6s)
    sleep 0.5;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 5   # restart #2 (~1.1s), budget exhausted
    sleep 1.0;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 6   # quarantined (~2.1s); stays stable -> revalidated (rebind restart #3)
    sleep 1.0;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 7   # normal op resumed, restart #4 (~3.1s)
) &
REVAL_PID=$!
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=4 \
OPENPOLARIS_USB_MAX_RESTARTS=2 OPENPOLARIS_USB_MAX_POLLS=200 \
sh "$SUPERVISOR" > "$TMP/revalidate.out" 2>&1
wait "$REVAL_PID" 2>/dev/null || true
# The quarantined identity (6) revalidated after staying stable. Leaving the
# quarantine now requires a bounded rebind (a successful restart-helper run that
# proves a usable pgphoto/PTP session), so revalidation fires its own restart
# before resetting the budget; the later change to 7 then restarts again.
# Total: 4->5 (restart #1), 5->6 (restart #2, budget exhausted -> quarantine),
# rebind on stable identity 6 (restart #3, leaves quarantine), 6->7 (restart #4,
# after revalidation reset the budget).
test "$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0)" = "4"
grep -q 'revalidated' "$TMP/revalidate.out"

# Issue #119 (TA follow-up): a FAILED bounded rebind must keep the supervisor
# degraded -- it must NOT clear quarantine or reset the budget on identity
# stability alone. The restart helper here ALWAYS fails, so the quarantine-exit
# rebind cannot prove a usable pgphoto/PTP session: the supervisor logs
# `bounded rebind failed` and stays quarantined (degraded) even though the USB
# identity is stable. This proves sysfs stability is not equated with a healthy
# session. (The two churn restarts also fail, but that only exercises the
# existing "restart failed; identity accepted" branch -- the assertion below is
# on the rebind-failure log line, which only the quarantine-exit path emits.)
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
cat > "$TMP/restart-always-fail" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod +x "$TMP/restart-always-fail"
(
    sleep 0.5;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 4   # churn restart #1 (~0.6s)
    sleep 0.5;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 5   # churn restart #2 (~1.1s), budget exhausted
    sleep 0.5;  remove_usb 1-1; make_usb 1-1 25fb 0183 1 6   # 5->6 stable change, budget exhausted -> QUARANTINE (qcandidate=6)
    sleep 1.5   # identity 6 stable for COOLDOWN polls -> rebind attempt fails -> stays degraded
) &
REBIND_PID=$!
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart-always-fail \
OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=4 \
OPENPOLARIS_USB_MAX_RESTARTS=2 OPENPOLARIS_USB_MAX_POLLS=200 \
sh "$SUPERVISOR" > "$TMP/rebind-fail.out" 2>&1
wait "$REBIND_PID" 2>/dev/null || true
# The failed rebind kept the supervisor degraded: it logged the rebind failure
# and did NOT clear quarantine / reset the budget on identity stability alone.
grep -q 'bounded rebind failed' "$TMP/rebind-fail.out"

# Issue #126: with the selected camera known, an UNRELATED second camera from any
# supported vendor must not change the fingerprint (no restart), while the
# selected camera's own re-enumeration still triggers exactly one bounded rebind.
rm -rf "$TMP/run/openpolaris-camera-usb-supervisor.lock"
: > "$RESTART_LOG"
make_usb 1-1 25fb 0183 1 3          # K-3 III (selected)
make_usb 1-2 04a9 0001 1 7          # unrelated Canon
(
    sleep 0.6;  make_usb 1-2 04a9 0001 1 8   # Canon re-enumerates (unrelated)
    sleep 0.6;  remove_usb 1-2        # Canon removed (unrelated)
    sleep 0.6;  make_usb 1-1 25fb 0183 1 4   # K-3 III's OWN re-enumeration -> 1 restart
    sleep 0.6
) &
SEL_PID=$!
: > "$TMP/selected.out"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_PROC_ROOT="$TMP/proc" OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" \
OPENPOLARIS_USB_POLL_SECS=0.1 OPENPOLARIS_USB_STABLE_POLLS=2 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=4 \
OPENPOLARIS_USB_MAX_RESTARTS=6 OPENPOLARIS_USB_MAX_POLLS=200 \
OPENPOLARIS_USB_SELECTED_VENDOR=25fb OPENPOLARIS_USB_SELECTED_PRODUCT=0183 \
sh "$SUPERVISOR" > "$TMP/selected.out" 2>&1 &
SUP_PID=$!
wait "$SEL_PID" 2>/dev/null || true
# Give the supervisor a moment to observe the final stable state, then stop it.
sleep 0.4
kill "$SUP_PID" 2>/dev/null || true
wait "$SUP_PID" 2>/dev/null || true
# Exactly ONE restart: only the K-3 III's own devnum change (3->4) counts; the
# Canon attach/re-enumerate/remove did not.
test "$(wc -l < "$RESTART_LOG")" -eq 1
grep -q 'stable identity change' "$TMP/selected.out"

# Issue #347: a camera that vanishes and never returns must be reported, not
# polled silently forever. In the captured session a goto slew took the K-3 III
# off USB; the supervisor logged the transition to `none`, restarted pgphoto, and
# then produced no further output for the rest of the session -- post-mortem had
# to be reconstructed by hand from two files. Assert:
#   * exactly ONE camera_absent line naming the identity that disappeared;
#   * a camera never present at boot is NOT treated as an absence;
#   * a return closes the episode with camera_returned.
#
# These must not depend on wall-clock races: the supervisor runs with MAX_POLLS=0
# (never self-exits) and the test waits for the expected line, then terminates it.
# Relying on a fixed poll budget instead made this flaky under harness load -- the
# budget could be exhausted before the removal was observed, so no announcement
# ever fired and the assertion failed for the wrong reason.
# The supervisor takes its baseline identity BEFORE the first poll, so the body
# must be removed only after that baseline is logged. Removing it immediately
# races startup: the supervisor then starts with an empty baseline, nothing was
# ever "seen", and no absence can be reported.
wait_for_baseline() {
    wait_for_log "$1" 'supervisor ready; identity=1-1|25fb:0189|1:3'
}

rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0189 1 3          # K-3 III present at boot
ABSENT_LOG=$TMP/absent.out
: > "$ABSENT_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=1 OPENPOLARIS_USB_STABLE_POLLS=2 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=2 OPENPOLARIS_USB_MAX_RESTARTS=6 \
OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=5 OPENPOLARIS_USB_MAX_POLLS=0 \
    sh "$SUPERVISOR" >"$ABSENT_LOG" 2>&1 &
absent_pid=$!
if ! wait_for_baseline "$ABSENT_LOG"; then
    kill "$absent_pid" 2>/dev/null || true; wait "$absent_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined the present camera (issue #347)"; exit 1
fi
remove_usb 1-1
if ! wait_for_log "$ABSENT_LOG" 'camera_absent'; then
    kill "$absent_pid" 2>/dev/null || true; wait "$absent_pid" 2>/dev/null || true
    echo "FAIL: no camera_absent line produced (issue #347)"; cat "$ABSENT_LOG"; exit 1
fi
# Let further polls run: the announcement must not repeat every poll.
sleep 0.5
kill "$absent_pid" 2>/dev/null || true; wait "$absent_pid" 2>/dev/null || true

test "$(grep -c 'camera_absent' "$ABSENT_LOG")" -eq 1
grep -q 'camera_absent: 1-1|25fb:0189|1:3' "$ABSENT_LOG"

# Issue #347 follow-up: losing the camera must also capture the kernel's view of
# the bus, because dmesg on the device rolls past the event before anyone can
# look. Bounded to one dump per episode for the same reason the announcement is.
grep -q 'usb-evidence: capturing kernel view after losing 1-1|25fb:0189|1:3' "$ABSENT_LOG"
test "$(grep -c 'usb-evidence: capturing' "$ABSENT_LOG")" -eq 1

# A camera absent from the very first poll was never present, so nothing was
# lost: no absence line at all.
rm -rf "$TMP/sys" "$TMP/run"
mkdir -p "$TMP/sys" "$TMP/run"
NEVER_LOG=$TMP/never.out
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=1 OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=3 \
OPENPOLARIS_USB_MAX_POLLS=20 sh "$SUPERVISOR" >"$NEVER_LOG" 2>&1
test "$(grep -c 'camera_absent' "$NEVER_LOG")" -eq 0
test "$(grep -c 'usb-evidence' "$NEVER_LOG")" -eq 0

# If the body comes back, the episode closes with a camera_returned line.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0189 1 3
RETURN_LOG=$TMP/camera-return.out
: > "$RETURN_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=1 OPENPOLARIS_USB_STABLE_POLLS=2 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=2 OPENPOLARIS_USB_MAX_RESTARTS=6 \
OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=3 OPENPOLARIS_USB_MAX_POLLS=0 \
    sh "$SUPERVISOR" >"$RETURN_LOG" 2>&1 &
return_pid=$!
if ! wait_for_baseline "$RETURN_LOG"; then
    kill "$return_pid" 2>/dev/null || true; wait "$return_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined the present camera (issue #347)"; exit 1
fi
remove_usb 1-1
if ! wait_for_log "$RETURN_LOG" 'camera_absent'; then
    kill "$return_pid" 2>/dev/null || true; wait "$return_pid" 2>/dev/null || true
    echo "FAIL: no camera_absent line before reattach (issue #347)"; exit 1
fi
make_usb 1-1 25fb 0189 1 9          # body returns on a new devnum
if ! wait_for_log "$RETURN_LOG" 'camera_returned'; then
    kill "$return_pid" 2>/dev/null || true; wait "$return_pid" 2>/dev/null || true
    echo "FAIL: no camera_returned line after reattach (issue #347)"; exit 1
fi
kill "$return_pid" 2>/dev/null || true; wait "$return_pid" 2>/dev/null || true

echo 'PASS: camera USB supervisor reports a camera that vanishes and never returns, once per episode (issue #347)'

# Issue #347 follow-up: the host runs usbcore.autosuspend=2, so an idle camera
# link is suspended after two seconds. Pinning is offered as an opt-in test
# knob only -- it must stay OFF by default (it changes device behaviour and is
# not proven to help) and must touch nothing but the camera device.
rm -rf "$TMP/sys" "$TMP/run"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0189 1 3
make_usb 1-2 1234 5678 1 4          # unrelated device: must never be pinned
PIN_DEFAULT=$TMP/pin_default.out
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=1 OPENPOLARIS_USB_MAX_POLLS=6 \
sh "$SUPERVISOR" >"$PIN_DEFAULT" 2>&1
test "$(grep -c 'usb-power' "$PIN_DEFAULT")" -eq 0
test "$(cat "$TMP/sys/1-1/power/control")" = "auto"

rm -rf "$TMP/run"
mkdir -p "$TMP/run"
PIN_ON=$TMP/pin_on.out
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=1 OPENPOLARIS_USB_MAX_POLLS=6 \
OPENPOLARIS_USB_PIN_POWER=1 sh "$SUPERVISOR" >"$PIN_ON" 2>&1
grep -q 'usb-power: pinned 25fb:0189 power/control=on' "$PIN_ON"
test "$(cat "$TMP/sys/1-1/power/control")" = "on"
# The unrelated device must be left alone, and the pin must not repeat per poll.
test "$(cat "$TMP/sys/1-2/power/control")" = "auto"
test "$(grep -c 'usb-power: pinned' "$PIN_ON")" -eq 1

echo 'PASS: camera USB supervisor leaves USB power policy alone by default and pins only the camera when opted in (issue #347)'

echo 'PASS: camera USB supervisor keys the fingerprint to the selected camera and ignores unrelated cameras (issue #126)'
echo 'PASS: camera USB supervisor validates lock ownership and restarts once after a stable camera identity change (issue #57)'
echo 'PASS: camera USB supervisor preserves pending identity and retries after a competing restart lock clears'
echo 'PASS: camera USB supervisor absorbs startup re-enumeration without restarting, then resumes normal restart logic (issue #121)'
echo 'PASS: camera USB supervisor bounds the restart budget under a re-enumeration flap (issue #119 churn guard)'
echo 'PASS: camera USB supervisor quarantines post-budget identity changes and requires revalidation before resuming (issue #119 TA follow-up)'
echo 'PASS: camera USB supervisor stays degraded when the quarantine-exit rebind fails, then resumes on a successful rebind (issue #119 TA follow-up)'

# Replay the late arrival on ports 003 and 004. The USB node and marker
# must belong to the same current process and current device inode.
for scenario in healthy3 healthy4 failed stale_generation reused_address; do
    rm -rf "$TMP/sys" "$TMP/proc" "$TMP/dev" "$TMP/run" "$RESTART_LOG"
    mkdir -p "$TMP/sys" "$TMP/proc/123/fd" "$TMP/dev/001" "$TMP/run"
    dev=3
    [ "$scenario" != healthy4 ] || dev=4
    node=$(printf '%s/dev/001/%03d' "$TMP" "$dev")
    touch "$node"
    inode=$(stat -c %i "$node")
    ln -s /app/lib/stage2/pgphoto.stage2ondisk "$TMP/proc/123/exe"
    ln -s "$node" "$TMP/proc/123/fd/7"
    marker_dir=$TMP/proc/123/fd
    if [ "$scenario" = stale_generation ]; then
        marker_dir=$TMP/proc/122/fd
        mkdir -p "$marker_dir"
    fi
    [ "$scenario" != reused_address ] || inode=0
    if [ "$scenario" != failed ]; then
        ln -s "$TMP/run/pgphoto-bound-1-$dev-$inode-ABCDEF (deleted)" "$marker_dir/8"
    fi
    : > "$TMP/arrival.out"   # fresh log: never match a previous test's output
    OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
    OPENPOLARIS_USB_DEVFS=$TMP/dev OPENPOLARIS_PROC_ROOT=$TMP/proc \
    OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
    OPENPOLARIS_USB_STARTUP_GRACE_POLLS=1 OPENPOLARIS_USB_MAX_POLLS=15 \
    sh "$SUPERVISOR" > "$TMP/arrival.out" &
    pid=$!
    sleep 0.2
    make_usb 1-1.4 25fb 0189 1 "$dev"
    wait "$pid"
    case "$scenario" in
        healthy*) grep -q 'adopting active pgphoto binding' "$TMP/arrival.out"
                  test ! -e "$RESTART_LOG" ;;
        *) test "$(wc -l < "$RESTART_LOG")" -eq 1 ;;
    esac
done

# Issue #358 acceptance task 2: "confirm whether restart is triggered while USB
# absent". It was. Reproduced against a fake sysfs before the fix: unplug a
# baselined body and the supervisor logged
#   stable identity change: <id> -> none; restarting pgphoto
# and spent one of MAX_RESTARTS on a restart that provably binds nothing -- there
# is no device for the new process to open. When the body came back, baseline was
# now "none", so a SECOND restart fired: two full dlopen + 64-shim cycles for one
# unplug/replug, against a budget of six (#119). That is the churn #119 was
# written to stop, re-opened by the absence path.
#
# The fix must NOT simply skip the restart while absent. Keeping the old baseline
# would make a same-address reconnect look unchanged (current == baseline) and
# skip the restart entirely, leaving pgphoto holding an fd to a device node the
# kernel already invalidated. Absence is therefore adopted as a KNOWN state by
# clearing the baseline, so any return -- same or different address -- is seen as
# a change and gets exactly one restart.

# (a) A body that vanishes and stays gone must not be restarted for.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0189 1 3
NO_RESTART_LOG=$TMP/no-restart.out
: > "$NO_RESTART_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_STABLE_POLLS=1 OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 \
OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=2 OPENPOLARIS_USB_ABSENT_EVIDENCE=0 \
OPENPOLARIS_USB_MAX_POLLS=0 sh "$SUPERVISOR" >"$NO_RESTART_LOG" 2>&1 &
nr_pid=$!
if ! wait_for_baseline "$NO_RESTART_LOG"; then
    kill "$nr_pid" 2>/dev/null || true; wait "$nr_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined the present camera (issue #358)"; exit 1
fi
remove_usb 1-1
if ! wait_for_log "$NO_RESTART_LOG" 'body absent; not restarting pgphoto'; then
    kill "$nr_pid" 2>/dev/null || true; wait "$nr_pid" 2>/dev/null || true
    echo "FAIL: supervisor restarted pgphoto while the bus was empty (issue #358)"
    cat "$NO_RESTART_LOG"; exit 1
fi
# Let further polls run so a later poll cannot sneak a restart in.
sleep 0.4
kill "$nr_pid" 2>/dev/null || true; wait "$nr_pid" 2>/dev/null || true
test ! -e "$RESTART_LOG"

# (b) The same body returning on the SAME bus/devnum must still get exactly one
# restart. This is the trap the naive fix falls into: if absence left the old
# baseline in place, current == baseline on return and pgphoto would keep an
# invalidated fd.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0189 1 3
RETURN_LOG=$TMP/absent-then-return.out
: > "$RETURN_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 \
OPENPOLARIS_USB_STABLE_POLLS=1 OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 \
OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=2 OPENPOLARIS_USB_ABSENT_EVIDENCE=0 \
OPENPOLARIS_USB_MAX_POLLS=0 sh "$SUPERVISOR" >"$RETURN_LOG" 2>&1 &
rt_pid=$!
if ! wait_for_baseline "$RETURN_LOG"; then
    kill "$rt_pid" 2>/dev/null || true; wait "$rt_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined the present camera (issue #358)"; exit 1
fi
remove_usb 1-1
wait_for_log "$RETURN_LOG" 'body absent; not restarting pgphoto' || {
    kill "$rt_pid" 2>/dev/null || true; wait "$rt_pid" 2>/dev/null || true
    echo "FAIL: no absence notice before reattach (issue #358)"; cat "$RETURN_LOG"; exit 1
}
make_usb 1-1 25fb 0189 1 3          # identical identity returns
if ! wait_for_log "$RETURN_LOG" 'stable identity change: none -> 1-1|25fb:0189|1:3'; then
    kill "$rt_pid" 2>/dev/null || true; wait "$rt_pid" 2>/dev/null || true
    echo "FAIL: same-address reconnect did not trigger a rebind (issue #358)"
    cat "$RETURN_LOG"; exit 1
fi
sleep 0.4
kill "$rt_pid" 2>/dev/null || true; wait "$rt_pid" 2>/dev/null || true
test "$(count_matches "$RESTART_LOG" restart)" -eq 1 || {
    echo "FAIL: same-address reconnect cost $(count_matches "$RESTART_LOG" restart) restarts, expected 1 (#358)"
    cat "$RETURN_LOG"; exit 1
}

echo 'PASS: camera USB supervisor does not restart for an absent body, and rebinds once on same-address reconnect (issue #358)'

# Issue #358 task 4: distinguish RESTARTED_PROCESS, USB_PRESENT, CAMERA_INIT_OK
# and PREVIEW_READY. In the captured v104 session both supervisor restarts were
# logged as successful -- new PID, :8080 listening -- while the second camera
# initialization had in fact failed, and the log was read as a recovery. These
# assertions pin that "restarted" and "bound" are reported as separate facts, so
# that combination is visible rather than inferred as health.
#
# Uses a K-1 II (25fb:0183), not a K-3 III. The bind probe was previously reached
# only through already_bound_k3iii(), which hard-codes 25fb:0189, so a K-1 II could
# never be evaluated as bound at all. camera_bound() is model-agnostic -- the
# pgphoto-bound marker from stage2_loader.c is keyed on bus/dev/inode -- and this
# is what that generalisation buys.

# (a) A genuinely bound body reports camera_init_ok=1.
rm -rf "$TMP/sys" "$TMP/proc" "$TMP/dev" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/proc/123/fd" "$TMP/dev/001" "$TMP/run"
node=$TMP/dev/001/003
touch "$node"
inode=$(stat -c %i "$node")
ln -s /app/lib/stage2/pgphoto.stage2ondisk "$TMP/proc/123/exe"
ln -s "$node" "$TMP/proc/123/fd/7"
ln -s "$TMP/run/pgphoto-bound-1-3-$inode-ABCDEF (deleted)" "$TMP/proc/123/fd/8"
make_usb 1-2 25fb 0183 1 3
BOUND_LOG=$TMP/bound.out
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_USB_DEVFS="$TMP/dev" OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 OPENPOLARIS_USB_MAX_POLLS=6 \
    sh "$SUPERVISOR" >"$BOUND_LOG" 2>&1
grep -q 'camera-state: usb_present=1 camera_init_ok=1 restarted_process=0 preview_ready=not-measured' "$BOUND_LOG" \
    || { echo "FAIL: bound K-1 II not reported as camera_init_ok=1 (issue #358)"; cat "$BOUND_LOG"; exit 1; }

# (b) A restart with no bind must report restarted_process=1 AND camera_init_ok=0.
# This is the exact state the v104 log described as success.
rm -rf "$TMP/sys" "$TMP/proc" "$TMP/dev" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/dev/001" "$TMP/run"
touch "$TMP/dev/001/003"
make_usb 1-2 25fb 0183 1 3          # present, but nothing is bound to it
UNBOUND_LOG=$TMP/unbound.out
: > "$UNBOUND_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_USB_DEVFS="$TMP/dev" OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 OPENPOLARIS_USB_STABLE_POLLS=1 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 OPENPOLARIS_USB_MAX_POLLS=0 \
    sh "$SUPERVISOR" >"$UNBOUND_LOG" 2>&1 &
ub_pid=$!
wait_for_log "$UNBOUND_LOG" 'camera-state: usb_present=1 camera_init_ok=0 restarted_process=0' || {
    kill "$ub_pid" 2>/dev/null || true; wait "$ub_pid" 2>/dev/null || true
    echo "FAIL: no camera-state line for an unbound present body (issue #358)"
    cat "$UNBOUND_LOG"; exit 1
}
printf '4\n' > "$TMP/sys/1-2/devnum"     # re-enumeration -> restart
if ! wait_for_log "$UNBOUND_LOG" 'camera-state: usb_present=1 camera_init_ok=0 restarted_process=1'; then
    kill "$ub_pid" 2>/dev/null || true; wait "$ub_pid" 2>/dev/null || true
    echo "FAIL: restart without a bind did not report camera_init_ok=0 (issue #358)"
    cat "$UNBOUND_LOG"; exit 1
fi
kill "$ub_pid" 2>/dev/null || true; wait "$ub_pid" 2>/dev/null || true

# (c) PREVIEW_READY is reported as not-measured, never as a guessed value. Frames
# go from pgphoto's :8080 stream to polaris-httpd, a separate process on a port
# this script does not know; camera-layer-report.sh reads opcode 292 from httpd's
# /api/link for it. Inventing a plausible value here would repeat the error this
# task exists to fix.
grep -q 'preview_ready=not-measured' "$BOUND_LOG" || { echo "FAIL: preview_ready not reported as not-measured (issue #358)"; exit 1; }
if grep -qE 'preview_ready=(1|yes|true)' "$BOUND_LOG" "$UNBOUND_LOG"; then
    echo "FAIL: preview_ready reported as a measured value (issue #358)"; exit 1
fi

echo 'PASS: camera USB supervisor reports usb_present/camera_init_ok/restarted_process separately and leaves preview_ready unmeasured (issue #358)'

# Issue #358 task 3, remaining scenarios that are testable at this layer.
#
# "USB port unavailable" here means the inconsistency the v104 evidence actually
# shows: sysfs still lists the body (so a fingerprint is produced) while the
# /dev/bus/usb node the process would have to open is gone. Clog_000003 reports
# abilities identifying a K-1 II while 'usb:001,003' cannot be found, followed by
# sp_Gphoto_Init ret -5 -- i.e. present-but-unopenable. That state must read as
# usb_present=1 camera_init_ok=0, not as healthy and not as absent.
rm -rf "$TMP/sys" "$TMP/proc" "$TMP/dev" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/proc/123/fd" "$TMP/dev/001" "$TMP/run"
make_usb 1-2 25fb 0183 1 3          # sysfs says the body is there
# ...but no node exists at /dev/bus/usb/001/003, and a pgphoto process is running.
ln -s /app/lib/stage2/pgphoto.stage2ondisk "$TMP/proc/123/exe"
PORT_LOG=$TMP/port.out
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_USB_DEVFS="$TMP/dev" OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 OPENPOLARIS_USB_MAX_POLLS=6 \
    sh "$SUPERVISOR" >"$PORT_LOG" 2>&1
grep -q 'camera-state: usb_present=1 camera_init_ok=0 restarted_process=0' "$PORT_LOG" \
    || { echo "FAIL: sysfs-present but devfs-missing not reported as init_ok=0 (#358 task 3)"
         cat "$PORT_LOG"; exit 1; }

# Repeated unplug/replug cycles. Each cycle must cost exactly one restart, and the
# state line must track every transition rather than latching on the first healthy
# reading. With MAX_RESTARTS unset (6) four cycles must not trip quarantine -- if
# absence were still restarting, four cycles would spend eight slots and quarantine
# on the third, which is how the original churn reached a device.
#
# wait_for_log() only answers "has this line ever appeared", so reusing it per
# cycle returns instantly from cycle 1 onward and the test would pass while
# asserting nothing. These cycles are driven off occurrence counts instead.
rm -rf "$TMP/sys" "$TMP/proc" "$TMP/dev" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/dev/001" "$TMP/run"
touch "$TMP/dev/001/003"
make_usb 1-2 25fb 0183 1 3
CYCLE_LOG=$TMP/cycle.out
: > "$CYCLE_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_USB_DEVFS="$TMP/dev" OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 OPENPOLARIS_USB_STABLE_POLLS=1 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=2 \
OPENPOLARIS_USB_ABSENT_EVIDENCE=0 OPENPOLARIS_USB_MAX_POLLS=0 \
    sh "$SUPERVISOR" >"$CYCLE_LOG" 2>&1 &
cy_pid=$!
wait_for_log "$CYCLE_LOG" 'supervisor ready' || {
    kill "$cy_pid" 2>/dev/null || true; wait "$cy_pid" 2>/dev/null || true
    echo "FAIL: supervisor never baselined for the cycle test (#358 task 3)"; exit 1
}
cycle=0
while [ "$cycle" -lt 4 ]; do
    cycle=$((cycle + 1))
    remove_usb 1-2
    if ! wait_for_count "$CYCLE_LOG" 'body absent; not restarting pgphoto' "$cycle" 800; then
        kill "$cy_pid" 2>/dev/null || true; wait "$cy_pid" 2>/dev/null || true
        echo "FAIL: cycle $cycle produced no NEW absence notice (#358 task 3)"
        cat "$CYCLE_LOG"; exit 1
    fi
    make_usb 1-2 25fb 0183 1 3
    if ! wait_for_count "$RESTART_LOG" 'restart' "$cycle" 800; then
        kill "$cy_pid" 2>/dev/null || true; wait "$cy_pid" 2>/dev/null || true
        echo "FAIL: after cycle $cycle expected $cycle restarts, got \
$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0) (#358 task 3)"
        cat "$CYCLE_LOG"; exit 1
    fi
done
sleep 0.4
kill "$cy_pid" 2>/dev/null || true; wait "$cy_pid" 2>/dev/null || true
test "$(count_matches "$RESTART_LOG" restart)" -eq 4 || {
    echo "FAIL: 4 unplug/replug cycles did not cost exactly 4 restarts (#358 task 3)"
    cat "$CYCLE_LOG"; exit 1
}
if grep -q 'restart_budget_exhausted' "$CYCLE_LOG"; then
    echo "FAIL: 4 cycles exhausted the restart budget (#358 task 3)"; exit 1
fi
# Four cycles must have produced four distinct absence notices and four restarts,
# i.e. one each -- not two per cycle.
test "$(count_matches "$CYCLE_LOG" 'body absent; not restarting pgphoto')" -eq 4

echo 'PASS: camera USB supervisor reports present-but-unopenable as init_ok=0 and costs one restart per unplug/replug cycle (issue #358 task 3)'

# Issue #358 task 5 (partial): supervisor events must be correlatable with
# pgphoto's own log lines. Across every Clog in
# docs/evidence/v117-k1ii-regression-20261125, 0 of 181 [camera-usb] lines carry
# a timestamp while every sp_Gphoto_Init / port line does. "The supervisor
# restarted and then init failed" therefore cannot be established from the log --
# only inferred from line order in a merged file, which is how the v104 restarts
# came to be read as a recovery. Pin that every supervisor line is timestamped.
rm -rf "$TMP/sys" "$TMP/run" "$TMP/proc" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run" "$TMP/proc"
make_usb 1-2 25fb 0183 1 3
TS_LOG=$TMP/ts.out
: > "$TS_LOG"   # fresh log: never match a previous test's output
OPENPOLARIS_RUN_DIR="$TMP/run" OPENPOLARIS_USB_SYSFS="$TMP/sys" \
OPENPOLARIS_PROC_ROOT="$TMP/proc" \
OPENPOLARIS_RESTART_GPHOTO="$TMP/restart" OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_STARTUP_GRACE_POLLS=0 OPENPOLARIS_USB_STABLE_POLLS=1 \
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=1 OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS=2 \
OPENPOLARIS_USB_MAX_POLLS=0 sh "$SUPERVISOR" >"$TS_LOG" 2>&1 &
ts_pid=$!
wait_for_log "$TS_LOG" 'supervisor ready' || {
    kill "$ts_pid" 2>/dev/null || true; wait "$ts_pid" 2>/dev/null || true
    echo "FAIL: supervisor produced no output for the timestamp test (#358 task 5)"; exit 1
}
remove_usb 1-2
wait_for_log "$TS_LOG" 'body absent' || {
    kill "$ts_pid" 2>/dev/null || true; wait "$ts_pid" 2>/dev/null || true
    echo "FAIL: no absence line for the timestamp test (#358 task 5)"; exit 1
}
sleep 0.3
kill "$ts_pid" 2>/dev/null || true; wait "$ts_pid" 2>/dev/null || true
total=$(count_matches "$TS_LOG" '\[camera-usb\]')
[ "$total" -gt 0 ] || { echo "FAIL: no [camera-usb] lines to check (#358 task 5)"; exit 1; }
untimed=$(grep '\[camera-usb\]' "$TS_LOG" | grep -vcE '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' | head -1) || untimed=0
test "$untimed" -eq 0 || {
    echo "FAIL: $untimed of $total [camera-usb] lines are untimestamped (#358 task 5)"
    cat "$TS_LOG"; exit 1
}

echo 'PASS: every camera USB supervisor line is timestamped so it can be correlated with pgphoto (issue #358 task 5)'
