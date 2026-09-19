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

# Issue #119: live-view churn / USB disappearance. A fast re-enumeration flap
# (device-number keeps changing while previewing) must not restart pgphoto on
# every poll -- that is the dlopen + 64-shim churn that drains the battery and
# drops the camera off USB. The bounded restart budget caps the total restarts;
# once exhausted the supervisor accepts the current identity and stops re-dlopening.
rm -rf "$TMP/sys" "$TMP/run" "$RESTART_LOG"
mkdir -p "$TMP/sys" "$TMP/run"
make_usb 1-1 25fb 0183 1 3
# Keep flapping the device number: each new identity persists for ~10 polls
# (one flap period) before the next appears, so each is "stable" enough to be a
# restart candidate. With RESTART_COOLDOWN_POLLS=2 that comfortably exceeds the
# required stable-poll count, so each identity triggers a restart until the
# budget is spent.
(
    n=4
    while :; do
        sleep 0.5
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
OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS=2 \
OPENPOLARIS_USB_MAX_RESTARTS=2 OPENPOLARIS_USB_MAX_POLLS=40 \
sh "$SUPERVISOR" > "$TMP/churn.out" 2>&1
kill "$FLAP2" 2>/dev/null; wait "$FLAP2" 2>/dev/null || true
# The restart budget (2) caps the total restarts even though the identity kept
# changing -- the dlopen loop ends instead of running for the whole window.
test "$(grep -c restart "$RESTART_LOG" 2>/dev/null || echo 0)" = "2"
grep -q 'restart budget' "$TMP/churn.out"

echo 'PASS: camera USB supervisor validates lock ownership and restarts once after a stable camera identity change (issue #57)'
echo 'PASS: camera USB supervisor absorbs startup re-enumeration without restarting, then resumes normal restart logic (issue #121)'
echo 'PASS: camera USB supervisor bounds the restart budget under a re-enumeration flap (issue #119 churn guard)'
