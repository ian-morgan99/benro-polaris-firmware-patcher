#!/bin/sh
# Restart pgphoto when a supported camera's USB identity changes. pgphoto keeps
# its selected CameraAbilities and usb:BUS,DEVICE port across an in-process
# reset, so a detach/reattach or body swap can otherwise leave it permanently
# retrying a port which no longer exists (issue #57).

RUN_DIR=${OPENPOLARIS_RUN_DIR:-/var/run}
SYSFS_USB=${OPENPOLARIS_USB_SYSFS:-/sys/bus/usb/devices}
RESTART=${OPENPOLARIS_RESTART_GPHOTO:-/app/restart_gphoto}
POLL_SECS=${OPENPOLARIS_USB_POLL_SECS:-1}
STABLE_POLLS=${OPENPOLARIS_USB_STABLE_POLLS:-2}
MAX_POLLS=${OPENPOLARIS_USB_MAX_POLLS:-0}
# Issue #121: startup-order crash. When the camera is already powered on at app
# launch, a transient re-enumeration during Benro Connect's own initialisation
# (device-number change) can fire a pgphoto restart that races the initial
# session open and crashes it. Suppress restarts for a bounded number of polls
# after the supervisor starts: identity changes in that window are absorbed into
# the baseline (so a later genuine change is still detected) instead of
# restarting. This is a bounded readiness condition, not an arbitrary sleep —
# after the window the normal debounce/restart logic resumes unchanged.
STARTUP_GRACE_POLLS=${OPENPOLARIS_USB_STARTUP_GRACE_POLLS:-3}
LOCKDIR=$RUN_DIR/openpolaris-camera-usb-supervisor.lock
PROC_ROOT=${OPENPOLARIS_PROC_ROOT:-/proc}

pid_is_supervisor() {
    [ -n "$1" ] && [ -d "$PROC_ROOT/$1" ] || return 1
    cmd=$(tr '\0' '\n' < "$PROC_ROOT/$1/cmdline" 2>/dev/null)
    case "$cmd" in
        *camera_usb_supervisor.sh) return 0 ;;
        *) return 1 ;;
    esac
}

camera_vendor() {
    case "$1" in
        04a9|04b0|04cb|04da|054c|07b4|25fb) return 0 ;;
        *) return 1 ;;
    esac
}

fingerprint() {
    for d in "$SYSFS_USB"/*; do
        [ -r "$d/idVendor" ] && [ -r "$d/idProduct" ] || continue
        vendor=$(tr 'A-F' 'a-f' < "$d/idVendor" 2>/dev/null)
        camera_vendor "$vendor" || continue
        product=$(tr 'A-F' 'a-f' < "$d/idProduct" 2>/dev/null)
        bus=$(cat "$d/busnum" 2>/dev/null)
        dev=$(cat "$d/devnum" 2>/dev/null)
        printf '%s|%s:%s|%s:%s\n' "${d##*/}" "$vendor" "$product" "$bus" "$dev"
    done | sort
}

if ! mkdir "$LOCKDIR" 2>/dev/null; then
    owner=$(cat "$LOCKDIR/pid" 2>/dev/null)
    case "$owner" in ''|*[!0-9]*) owner= ;; esac
    if pid_is_supervisor "$owner"; then
        exit 0
    fi
    rm -rf "$LOCKDIR"
    mkdir "$LOCKDIR" 2>/dev/null || exit 0
fi
echo $$ > "$LOCKDIR/pid"
cleanup() {
    owner=$(cat "$LOCKDIR/pid" 2>/dev/null)
    [ "$owner" = "$$" ] && rm -rf "$LOCKDIR"
}
trap 'exit 0' HUP INT TERM
trap 'cleanup' EXIT

baseline=$(fingerprint)
candidate=$baseline
stable=0
polls=0
echo "[camera-usb] supervisor ready; identity=${baseline:-none}"

while :; do
    sleep "$POLL_SECS"
    current=$(fingerprint)
    polls=$((polls + 1))

    # Issue #121: during the startup grace window, absorb identity changes into
    # the baseline without restarting pgphoto. A camera that is already powered
    # on at app launch can re-enumerate (device-number change) while Benro
    # Connect is still initialising; a restart there races the initial session
    # open and crashes it. After the window, adopt the current identity as the
    # new baseline so a later genuine change is still detected.
    if [ "$STARTUP_GRACE_POLLS" -gt 0 ] && [ "$polls" -le "$STARTUP_GRACE_POLLS" ]; then
        if [ "$current" != "$baseline" ]; then
            echo "[camera-usb] startup grace: absorbing identity change ${baseline:-none} -> ${current:-none} (no restart, poll $polls/$STARTUP_GRACE_POLLS)"
            baseline=$current
            candidate=$current
            stable=0
        fi
        [ "$MAX_POLLS" -gt 0 ] && [ "$polls" -ge "$MAX_POLLS" ] && exit 0
        continue
    fi

    if [ "$current" = "$baseline" ]; then
        candidate=$baseline
        stable=0
    elif [ "$current" = "$candidate" ]; then
        stable=$((stable + 1))
    else
        candidate=$current
        stable=1
    fi

    if [ "$stable" -ge "$STABLE_POLLS" ]; then
        echo "[camera-usb] stable identity change: ${baseline:-none} -> ${candidate:-none}; restarting pgphoto"
        if "$RESTART"; then
            baseline=$candidate
            stable=0
            echo "[camera-usb] pgphoto restart complete"
        else
            # Avoid a tight retry storm. A later identity transition can retry;
            # the existing restart helper already logs the bounded failure.
            baseline=$candidate
            stable=0
            echo "[camera-usb] pgphoto restart failed; identity accepted to prevent a loop" >&2
        fi
    fi

    [ "$MAX_POLLS" -gt 0 ] && [ "$polls" -ge "$MAX_POLLS" ] && exit 0
done
