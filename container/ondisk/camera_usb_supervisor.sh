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
# Issue #119: live-view churn / USB disappearance. When the camera re-enumerates
# (device-number change) while previewing, each detected identity change restarts
# pgphoto -- a full dlopen of core+port plus 64-shim re-registration. If that
# restart itself triggers another re-enumeration the supervisor loops (~36 dlopen
# cycles / 20 s observed), draining the battery and churning the PTP/USB link
# until the camera drops off USB. Two bounded guards break the loop:
#   RESTART_COOLDOWN_POLLS -- minimum polls between restarts, so a fast flap
#     cannot restart pgphoto on every poll; and
#   MAX_RESTARTS           -- a total restart budget. Once exhausted the
#     supervisor enters an explicit degraded/quarantine state (issue #119 TA
#     release-safety follow-up): it stops restarting, logs
#     `restart_budget_exhausted`, and does NOT adopt the current identity as
#     healthy. Normal operation resumes only after a positive stable-identity
#     condition (the identity stays unchanged for COOLDOWN consecutive polls)
#     revalidates it, so a genuinely reconnected camera is never silently
#     accepted while the existing pgphoto session is still bound to the old
#     device/session.
# Both are bounded readiness conditions, not arbitrary sleeps: after the budget
# is spent the supervisor still tracks identity, it just no longer re-dlopens.
RESTART_COOLDOWN_POLLS=${OPENPOLARIS_USB_RESTART_COOLDOWN_POLLS:-5}
MAX_RESTARTS=${OPENPOLARIS_USB_MAX_RESTARTS:-6}
# Issue #119 (TA follow-up): the quarantine-exit rebind requires the quarantined
# identity to stay stable for this many consecutive polls BEFORE the bounded
# rebind is attempted. Kept separate from COOLDOWN so tests can decouple "when
# the main loop quarantines" from "when the rebind fires". Defaults to 4 (the
# same order as the churn cooldown) -- a genuinely stable, reconnected camera
# clears it quickly; a flapping one never does.
REBIND_STABLE_POLLS=${OPENPOLARIS_USB_REBIND_STABLE_POLLS:-4}
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
restarts=0
# Issue #119 (TA release-safety follow-up): explicit degraded/quarantine state.
# When the restart budget is exhausted the supervisor must NOT adopt the current
# identity as healthy and stop restarting forever -- that can leave the existing
# pgphoto session bound to the old device/session while a genuinely reconnected
# camera is silently accepted. Instead it enters a quarantine: churn is
# suppressed, `restart_budget_exhausted` is logged, and normal operation resumes
# only after a positive stable-identity/readiness condition (the current identity
# stays unchanged for COOLDOWN consecutive polls) revalidates it.
# qcandidate/qstable track the quarantined identity's own stability so a
# positive revalidation condition is independent of the baseline/candidate
# tracking (which resets `stable` whenever the identity equals the baseline).
quarantined=0
qcandidate=""
qstable=0
# Issue #119: minimum polls between restarts. The stable-change detector already
# requires STABLE_POLLS consecutive identical polls; requiring the larger of that
# and RESTART_COOLDOWN_POLLS spaces out restarts so a fast re-enumeration flap
# cannot restart pgphoto on every poll (which is what drove the dlopen churn).
COOLDOWN=$STABLE_POLLS
[ "$RESTART_COOLDOWN_POLLS" -gt "$COOLDOWN" ] && COOLDOWN=$RESTART_COOLDOWN_POLLS
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

    if [ "$quarantined" = "1" ]; then
        # Issue #119 (TA release-safety follow-up): degraded/quarantine state.
        # The restart budget is exhausted, so churn is suppressed and the current
        # identity is NOT adopted as healthy. Normal operation resumes only after
        # a positive stable-identity/readiness condition: the quarantined
        # identity must stay unchanged for COOLDOWN consecutive polls before it
        # is revalidated. A further identity change resets that counter, so a
        # genuinely reconnected camera is never silently accepted while the
        # existing pgphoto session may still be bound to the old device/session.
        if [ "$current" = "$qcandidate" ]; then
            qstable=$((qstable + 1))
        else
            qcandidate=$current
            qstable=1
        fi
        if [ "$qstable" -ge "$REBIND_STABLE_POLLS" ]; then
            # Issue #119 (TA follow-up): sysfs identity stability alone does NOT
            # prove a usable pgphoto/PTP session -- the existing process may still
            # own a stale port/session from before the churn. Before leaving the
            # degraded/quarantine state, perform one bounded rebind: run the same
            # restart helper that re-dlopens core+port and re-registers the 64
            # shims against the current identity. Only if that rebind SUCCEEDS do
            # we clear quarantine and reset the budget; on failure we stay degraded
            # (qstable is held at the threshold so the next stable window retries)
            # rather than silently accepting a possibly-stale session as healthy.
            if "$RESTART"; then
                echo "[camera-usb] quarantined identity ${qcandidate:-none} revalidated after $qstable stable polls; bounded rebind succeeded, resuming normal operation (issue #119)"
                baseline=$qcandidate
                candidate=$baseline
                stable=0
                quarantined=0
                qcandidate=""
                qstable=0
                restarts=0
            else
                echo "[camera-usb] quarantined identity ${qcandidate:-none} stable for $qstable polls but bounded rebind failed; remaining degraded (issue #119)" >&2
                # Stay quarantined. Hold qstable at the threshold so the next poll
                # that keeps the identity stable immediately retries the rebind,
                # while any identity change resets qstable to 1 and re-arms it.
                qstable=$REBIND_STABLE_POLLS
            fi
        fi
    else
        if [ "$current" = "$baseline" ]; then
            candidate=$baseline
            stable=0
        elif [ "$current" = "$candidate" ]; then
            stable=$((stable + 1))
        else
            candidate=$current
            stable=1
        fi

        if [ "$stable" -ge "$COOLDOWN" ]; then
            if [ "$MAX_RESTARTS" -gt 0 ] && [ "$restarts" -ge "$MAX_RESTARTS" ]; then
                # Issue #119 (TA release-safety follow-up): restart budget
                # exhausted. Enter the explicit degraded/quarantine state instead
                # of adopting the new identity as healthy: churn is suppressed,
                # `restart_budget_exhausted` is logged, and normal operation
                # resumes only after a positive stable-identity condition
                # revalidates the quarantined identity (see the quarantine branch
                # above). This keeps a genuinely reconnected camera from being
                # silently accepted while the existing pgphoto session is still
                # bound to the old device/session.
                echo "[camera-usb] restart_budget_exhausted ($MAX_RESTARTS); quarantining identity ${candidate:-none} -- no further restarts until it revalidates (issue #119)" >&2
                quarantined=1
                qcandidate=$candidate
                qstable=0
            else
                echo "[camera-usb] stable identity change: ${baseline:-none} -> ${candidate:-none}; restarting pgphoto"
                if "$RESTART"; then
                    restarts=$((restarts + 1))
                    baseline=$candidate
                    stable=0
                    echo "[camera-usb] pgphoto restart complete (restart $restarts${MAX_RESTARTS:+/$MAX_RESTARTS})"
                else
                    # Avoid a tight retry storm. A later identity transition can retry;
                    # the existing restart helper already logs the bounded failure.
                    restarts=$((restarts + 1))
                    baseline=$candidate
                    stable=0
                    echo "[camera-usb] pgphoto restart failed; identity accepted to prevent a loop" >&2
                fi
            fi
        fi
    fi

    [ "$MAX_POLLS" -gt 0 ] && [ "$polls" -ge "$MAX_POLLS" ] && exit 0
done
