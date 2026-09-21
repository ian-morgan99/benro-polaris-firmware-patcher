#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SUPERVISOR=$ROOT/container/ondisk/camera_usb_supervisor.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/sys" "$TMP/run" "$TMP/proc"

make_usb() {
    dir=$TMP/sys/$1
    mkdir -p "$dir"
    printf '%s\n' "$2" > "$dir/idVendor"
    printf '%s\n' "$3" > "$dir/idProduct"
    printf '%s\n' "$4" > "$dir/busnum"
    printf '%s\n' "$5" > "$dir/devnum"
}

RESTART_LOG=$TMP/restarts
export RESTART_LOG
cat > "$TMP/restart" <<'EOF'
#!/bin/sh
printf 'restart\n' >> "$RESTART_LOG"
EOF
chmod +x "$TMP/restart"

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
    rm -rf "$TMP/sys/1-1"
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
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
(
    sleep 0.2   # past the 3-poll (0.15s) grace window
    rm -rf "$TMP/sys/1-1"
    make_usb 1-1 25fb 0183 1 9   # genuine body/device change after startup
) &
LATE_PID=$!
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_MAX_POLLS=12 sh "$SUPERVISOR" > "$TMP/post-grace.out"
wait "$LATE_PID" 2>/dev/null || true
# Exactly one restart after the grace window (file may be absent if none fired).
test "$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0)" = "1"

# Issue #121 (TA follow-up): a GENUINE camera disconnect/reconnect during the
# startup grace window. The grace window absorbs EVERY fingerprint change, not
# just same-body devnum churn -- so a real removal followed by a reconnect to a
# different device number in that interval is intentionally ignored and becomes
# the new baseline. This must NOT leave pgphoto bound to stale camera/session
# state: once the grace window closes, the reconnected (different) identity is a
# genuine change from what pgphoto originally bound to, so the normal debounce
# logic must fire exactly one restart to rebind it. A same-body reconnect that
# lands on the original identity would correctly need no restart; this case pins
# the different-identity path.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3   # camera present at supervisor start (baseline devnum 3)
(
    sleep 0.1; rm -rf "$TMP/sys/1-1"          # genuine disconnect during grace (~poll 2)
    sleep 0.1; make_usb 1-1 25fb 0183 1 9     # reconnect to a DIFFERENT devnum during grace (~poll 4)
) &
RECONNECT_PID=$!
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_PROC_ROOT=$TMP/proc \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_MAX_POLLS=12 sh "$SUPERVISOR" > "$TMP/grace-reconnect.out"
wait "$RECONNECT_PID" 2>/dev/null || true
# The grace window absorbed the disconnect+reconnect (no restart while polls<=3);
# after it closed, the reconnected devnum-9 identity is a genuine change from the
# original devnum-3 baseline, so exactly one restart fires to rebind pgphoto.
test "$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0)" = "1"
grep -q "startup grace: absorbing identity change" "$TMP/grace-reconnect.out"

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
    sleep 1.2; rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 4   # restart #1 (~t=1.4)
    sleep 1.2; rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 5   # restart #2 (~t=2.6), budget exhausted
    sleep 1.2; rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 6   # quarantine (~t=4.2)
    sleep 0.8   # hold identity 6 stable for ~16 polls (>> COOLDOWN=4): the quarantine triggers AND the rebind-on-revalidation fires deterministically (restart #3)
    n=7
    while :; do
        sleep 0.1
        rm -rf "$TMP/sys/1-1"
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
    sleep 1.2; rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 4   # restart #1 (~t=1.4)
    sleep 1.2; rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 5   # restart #2 (~t=2.6), budget exhausted
    sleep 1.2; rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 6   # quarantine (~t=4.2)
    sleep 0.3   # hold identity 6 for ~6 polls: enough for the main loop to quarantine (stable>=COOLDOWN=4) but, with REBIND_STABLE_POLLS=20, qstable never reaches the rebind threshold before the flap resets it -- so no 3rd restart fires
    n=7
    while :; do
        sleep 0.1
        rm -rf "$TMP/sys/1-1"
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
    sleep 0.5;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 4   # restart #1 (~0.6s)
    sleep 0.5;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 5   # restart #2 (~1.1s), budget exhausted
    sleep 1.0;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 6   # quarantined (~2.1s); stays stable -> revalidated (rebind restart #3)
    sleep 1.0;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 7   # normal op resumed, restart #4 (~3.1s)
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
    sleep 0.5;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 4   # churn restart #1 (~0.6s)
    sleep 0.5;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 5   # churn restart #2 (~1.1s), budget exhausted
    sleep 0.5;  rm -rf "$TMP/sys/1-1"; make_usb 1-1 25fb 0183 1 6   # 5->6 stable change, budget exhausted -> QUARANTINE (qcandidate=6)
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
    sleep 0.6;  rm -rf "$TMP/sys/1-2"        # Canon removed (unrelated)
    sleep 0.6;  make_usb 1-1 25fb 0183 1 4   # K-3 III's OWN re-enumeration -> 1 restart
    sleep 0.6
) &
SEL_PID=$!
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

echo 'PASS: camera USB supervisor keys the fingerprint to the selected camera and ignores unrelated cameras (issue #126)'
echo 'PASS: camera USB supervisor validates lock ownership and restarts once after a stable camera identity change (issue #57)'
echo 'PASS: camera USB supervisor absorbs startup re-enumeration without restarting, then resumes normal restart logic (issue #121)'
echo 'PASS: camera USB supervisor bounds the restart budget under a re-enumeration flap (issue #119 churn guard)'
echo 'PASS: camera USB supervisor quarantines post-budget identity changes and requires revalidation before resuming (issue #119 TA follow-up)'
echo 'PASS: camera USB supervisor stays degraded when the quarantine-exit rebind fails, then resumes on a successful rebind (issue #119 TA follow-up)'
