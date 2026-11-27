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
# If a restart is already in progress, restart_gphoto refuses to race it. Do
# not accept the new USB identity as healthy in that case: preserve the old
# baseline and retry the rebind after a short poll-based backoff.
RESTART_RETRY_POLLS=${OPENPOLARIS_USB_RESTART_RETRY_POLLS:-5}
# Issue #119 (TA follow-up): the quarantine-exit rebind requires the quarantined
# identity to stay stable for this many consecutive polls BEFORE the bounded
# rebind is attempted. Kept separate from COOLDOWN so tests can decouple "when
# the main loop quarantines" from "when the rebind fires". Defaults to 4 (the
# same order as the churn cooldown) -- a genuinely stable, reconnected camera
# clears it quickly; a flapping one never does.
REBIND_STABLE_POLLS=${OPENPOLARIS_USB_REBIND_STABLE_POLLS:-4}
# Issue #347: a goto slew took the K-3 III off USB mid-session and it never came
# back. The supervisor logged `stable identity change: 1-1.2|25fb:0189|1:3 ->
# none`, restarted pgphoto successfully, and then said nothing for the remaining
# 22 minutes of the session -- it just kept polling an empty bus. Post-mortem had
# to be reconstructed by hand from two log files, and `dmesg` retained no USB
# lines at all. This is the "say so loudly" half of #146's observability
# requirement; #146 itself owns the recovery half.
#   ABSENT_ANNOUNCE_POLLS -- after this many consecutive polls with an empty bus,
#     log one `camera_absent` line naming the identity that disappeared and how
#     long it has been gone. Announced once per absence episode, not every poll,
#     so a long outage costs one line rather than thousands. Set to 0 to disable.
# A camera that was never present at boot is not an absence: nothing was lost.
ABSENT_ANNOUNCE_POLLS=${OPENPOLARIS_USB_ABSENT_ANNOUNCE_POLLS:-30}
# Issue #347 follow-up: every post-mortem so far had to be reconstructed by hand
# from Clog/Mlog, and the kernel's side of the event was simply gone -- dmesg on
# this device retains only a few hundred lines and had already rolled past the
# drop. Mlog carries only userspace uevents, so the kernel's own reason (disconnect
# / reset failure / xhci halt) is never recoverable after the fact. Both recorded
# losses happened while a goto slew was running, and in one the kernel removed the
# camera 6 ms after `GotoAuTask: SP_GOTO_STA_WAIT_RESULT`, so the kernel view is
# the evidence we are missing. Dump it once, at the moment of loss.
#   ABSENT_EVIDENCE -- 0 disables the dump entirely.
ABSENT_EVIDENCE=${OPENPOLARIS_USB_ABSENT_EVIDENCE:-1}
# Issue #347 follow-up: candidate mitigation, opt-in. This host runs
# usbcore.autosuspend=2 with every device on power/control=auto, so an idle USB
# device is suspended after two seconds -- including a camera link. That is far
# more aggressive than a desktop would use for a PTP body, and a suspend/resume
# cycle landing mid-operation is a plausible way to lose the device outright.
# Pinning the camera's own interface to "on" removes that variable without
# touching global policy or any other device.
#   USB_PIN_POWER -- 1 pins each detected camera device's power/control to "on"
#     every poll; 0 (default) leaves kernel policy untouched.
# Deliberately default-off: it changes device behaviour, and #147 requires power
# changes to be made at the ownership layer with evidence rather than as a global
# governor. It is also NOT proven to help -- motor activity, not suspend timing,
# is what correlates with recovery so far. Enable it only to test it.
USB_PIN_POWER=${OPENPOLARIS_USB_PIN_POWER:-0}
# Issue #358: how often the expensive /proc bind probe runs while nothing has
# changed. 0 means "only on cheap changes" (identity or restart count), which
# never scans /proc in steady state.
CAMERA_STATE_PROBE_POLLS=${OPENPOLARIS_USB_STATE_PROBE_POLLS:-30}
LOCKDIR=$RUN_DIR/openpolaris-camera-usb-supervisor.lock
PROC_ROOT=${OPENPOLARIS_PROC_ROOT:-/proc}
# A literal newline for pattern matching. fingerprint() emits one line per camera,
# so a fingerprint containing a newline means more than one device matched and no
# single bind can be attributed to it. Written this way because a raw newline
# embedded in a case pattern is invisible to anyone reading the file.
nl='
'

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

# Issue #126: when the selected camera is known (OPENPOLARIS_USB_SELECTED_VENDOR /
# _PRODUCT, set by the pgphoto launcher from the port it actually opened), key the
# fingerprint to THAT camera only.  An unrelated second camera from any supported
# vendor (e.g. a Canon plugged in while a K-3 III session is live) must not change
# the identity and trigger a restart/quarantine of a healthy selected session.
# When the selection is unset we fall back to the aggregate camera-vendor scan so
# existing behaviour (and tests) are unchanged.  The selected camera's own
# re-enumeration (devnum change) still changes its fingerprint -> one bounded
# rebind; a body replacement (different product) or disappearance (empty) also
# changes it -> fresh-session / rebind path.
SELECTED_VENDOR=${OPENPOLARIS_USB_SELECTED_VENDOR:-}
SELECTED_PRODUCT=${OPENPOLARIS_USB_SELECTED_PRODUCT:-}

fingerprint() {
    for d in "$SYSFS_USB"/*; do
        [ -r "$d/idVendor" ] && [ -r "$d/idProduct" ] || continue
        vendor=$(tr 'A-F' 'a-f' < "$d/idVendor" 2>/dev/null)
        product=$(tr 'A-F' 'a-f' < "$d/idProduct" 2>/dev/null)
        if [ -n "$SELECTED_VENDOR" ]; then
            # Selected-camera mode: only the exact selected vendor+product counts.
            [ "$vendor" = "$(printf '%s' "$SELECTED_VENDOR" | tr 'A-F' 'a-f')" ] || continue
            [ -z "$SELECTED_PRODUCT" ] || [ "$product" = "$(printf '%s' "$SELECTED_PRODUCT" | tr 'A-F' 'a-f')" ] || continue
        else
            camera_vendor "$vendor" || continue
        fi
        bus=$(cat "$d/busnum" 2>/dev/null)
        dev=$(cat "$d/devnum" 2>/dev/null)
        printf '%s|%s:%s|%s:%s\n' "${d##*/}" "$vendor" "$product" "$bus" "$dev"
    done | sort
}

# Issue #358 task 4: distinguish RESTARTED_PROCESS, USB_PRESENT, CAMERA_INIT_OK
# and PREVIEW_READY.
#
# The reason this exists is the misdiagnosis it prevents. In the captured v104
# session both supervisor restarts were logged as successful -- new PID, :8080
# listening -- and the second camera initialization had in fact failed. A reader
# of that log concluded the camera had recovered. "pgphoto running" and "port open"
# are not camera state: a process restarted while the bus is empty satisfies both
# and binds nothing. These four flags are reported separately so that combination
# is visible instead of being inferred as health.
#
#   USB_PRESENT      sysfs shows a supported camera at all.
#   CAMERA_INIT_OK   camera_bound(): a live fd on the device node AND an open
#                    pgphoto-bound marker in the same process. The only evidence
#                    here that actually proves a usable session.
#   RESTARTED_PROCESS  this supervisor has restarted pgphoto at least once.
#   PREVIEW_READY    NOT MEASURED, deliberately. Frames flow from pgphoto's :8080
#                    MJPEG stream to polaris-httpd, which is a separate process on
#                    a port this script does not know. camera-layer-report.sh reads
#                    opcode 292 from httpd's /api/link for it; duplicating that
#                    here would mean the supervisor issuing HTTP to a service it
#                    has no contract with, and guessing the port. Reporting a
#                    plausible value would be worse than reporting none -- it is
#                    the same class of error as treating a restart as recovery.
#
# Emitted only when the tuple changes, so a steady state costs one line rather
# than one per poll.
#
# Cost: camera_bound() walks /proc/<pid>/fd for every process. The existing
# already_bound_k3iii did the same, but only when a stable identity change was
# already pending -- a rare event. Running it on every poll would put that scan in
# the steady-state path of a supervisor that polls once a second on an embedded
# head with UBIFS, and I have not measured it on hardware. So the expensive probe
# is bounded: it runs when something cheap has changed (identity, restart count)
# or every CAMERA_STATE_PROBE_POLLS polls, whichever comes first. Between those,
# the last known init_ok is carried forward and the line is not re-emitted anyway.
report_camera_state() {
    _cur=$1
    usb_present=0; [ -n "$_cur" ] && usb_present=1
    restarted=0; [ "$restarts" -gt 0 ] && restarted=1

    if [ "$usb_present" != "$last_usb_present" ] \
       || [ "$restarted" != "$last_restarted" ] \
       || [ "$_cur" != "$last_state_identity" ] \
       || { [ "$CAMERA_STATE_PROBE_POLLS" -gt 0 ] && [ $((polls % CAMERA_STATE_PROBE_POLLS)) -eq 0 ]; }; then
        init_ok=0; camera_bound "$_cur" && init_ok=1
        last_usb_present=$usb_present
        last_restarted=$restarted
        last_state_identity=$_cur
        state="usb_present=$usb_present camera_init_ok=$init_ok restarted_process=$restarted preview_ready=not-measured"
        if [ "$state" != "$last_reported_state" ]; then
            echo "[camera-usb] camera-state: $state identity=${_cur:-none} restarts=$restarts (issue #358)"
            last_reported_state=$state
        fi
    fi
}

# Is pgphoto actually bound to the camera described by this fingerprint?
#
# Evidence, all three required: a process whose exe is the stage-2 pgphoto binary,
# a live fd on the /dev/bus/usb node for that bus/dev, and an open link to the
# pgphoto-bound-<bus>-<dev>-<inode>-XXXXXX marker that container/stage2_loader.c
# creates only after a successful bind. The marker is keyed on bus/dev/inode, so
# it is model-agnostic: nothing about it is specific to any one body.
#
# This is the only probe in this script that proves a camera is usable. "pgphoto
# is running" and ":8080 is listening" prove neither -- a restarted process with
# no device satisfies both, which is exactly how #358's two restarts were logged
# as successful while the second camera init had in fact failed.
camera_bound() {
    _id=$1
    [ -n "$_id" ] || return 1
    case "$_id" in
        *"$nl"*) return 1 ;;   # more than one camera: cannot attribute a bind
    esac
    address=${_id##*|}
    bus=${address%:*}
    dev=${address#*:}
    # Must be "<bus>:<dev>" with both halves present. A fingerprint that is not
    # in that shape cannot be resolved to a device node, so it is not a bind.
    [ -n "$bus" ] && [ -n "$dev" ] || return 1
    [ "$address" != "$bus" ] || return 1
    node=$(printf '%s/%03d/%03d' "${OPENPOLARIS_USB_DEVFS:-/dev/bus/usb}" "$bus" "$dev") || return 1
    marker_dir=$(readlink -f "$RUN_DIR") || return 1
    inode=$(stat -c %i "$node" 2>/dev/null) || return 1
    for proc in "$PROC_ROOT"/[0-9]*; do
        [ "$(readlink "$proc/exe")" = "${OPENPOLARIS_STAGE2_DIR:-/app/lib/stage2}/pgphoto.stage2ondisk" ] || continue
        marker=
        usbfd=
        for fd in "$proc"/fd/*; do
            case "$(readlink "$fd")" in
                "$marker_dir/pgphoto-bound-$bus-$dev-$inode-"??????" (deleted)") marker=$fd ;;
            esac
            [ "$fd" -ef "$node" ] && usbfd=$fd
        done
        [ -n "$usbfd" ] && [ -n "$marker" ] && [ -L "$marker" ] && [ "$usbfd" -ef "$node" ] && return 0
    done
    return 1
}

# Only the observed single K-3 III late-arrival case can bypass a restart.
# Require both successful init and a live usbfs fd in the same executable.
#
# The model gate stays here deliberately. camera_bound() is model-agnostic, but
# this bypass -- adopting an identity without restarting pgphoto -- was only ever
# observed and qualified for a late-arriving K-3 III. Widening it would change
# restart semantics for every other body on evidence from one, so the restriction
# is kept and reporting uses camera_bound() directly instead.
already_bound_k3iii() {
    case "$1" in
        *'|25fb:0189|'*) ;;
        *) return 1 ;;
    esac
    camera_bound "$1"
}

# Issue #347 follow-up: capture the kernel's view of the bus at the instant the
# camera is lost. Every post-mortem to date had to be rebuilt from Clog/Mlog
# alone, and dmesg on this device holds only a few hundred lines -- by the time
# anyone looked it had already rolled past the drop, so the kernel side of the
# event was unrecoverable. Mlog carries only userspace uevents, so the kernel's
# own reason for the removal (disconnect / reset failure / xhci halt) never
# survives to be read. Both recorded losses happened while a goto slew was
# running, and in one the kernel removed the camera 6 ms after
# `GotoAuTask: SP_GOTO_STA_WAIT_RESULT`, which makes the kernel's report the
# decisive missing evidence.
#
# Read-only and strictly bounded: one dmesg tail, one module parameter, and the
# power/runtime state of whatever is still attached. Nothing here writes, resets,
# suspends or restarts anything -- recovery is #146's scope, not this one.
# Issue #347 follow-up: optionally keep the camera's USB interface out of runtime
# suspend. Only ever touches devices that already matched as a camera, never the
# hub or controller, and never writes anything else. Best-effort: sysfs may be
# read-only or the attribute absent, in which case this is a silent no-op.
pin_camera_power() {
    for d in "$SYSFS_USB"/*; do
        [ -r "$d/idVendor" ] && [ -r "$d/idProduct" ] || continue
        vendor=$(tr 'A-F' 'a-f' < "$d/idVendor" 2>/dev/null)
        product=$(tr 'A-F' 'a-f' < "$d/idProduct" 2>/dev/null)
        if [ -n "$SELECTED_VENDOR" ]; then
            [ "$vendor" = "$(printf '%s' "$SELECTED_VENDOR" | tr 'A-F' 'a-f')" ] || continue
            [ -z "$SELECTED_PRODUCT" ] || [ "$product" = "$(printf '%s' "$SELECTED_PRODUCT" | tr 'A-F' 'a-f')" ] || continue
        else
            camera_vendor "$vendor" || continue
        fi
        [ -w "$d/power/control" ] || continue
        [ "$(cat "$d/power/control" 2>/dev/null)" = "on" ] && continue
        echo on > "$d/power/control" 2>/dev/null \
            && echo "[camera-usb] usb-power: pinned ${vendor}:${product} power/control=on (autosuspend disabled for this device; issue #347)" >&2
    done
}

dump_usb_evidence() {
    lost="$1"
    echo "[camera-usb] usb-evidence: capturing kernel view after losing ${lost}" >&2
    if command -v dmesg >/dev/null 2>&1; then
        # Tail only: the ring buffer is small on this kernel and the interesting
        # lines (disconnect / reset / suspend-resume failures) are the newest.
        dmesg 2>/dev/null | grep -iE "usb|xhci|hub" | tail -25 >&2
    else
        echo "[camera-usb] usb-evidence: dmesg unavailable" >&2
    fi
    for p in /sys/module/usbcore/parameters/autosuspend \
             /sys/module/usbcore/parameters/blinkenlights; do
        [ -r "$p" ] && echo "[camera-usb] usb-evidence: ${p}=$(cat "$p" 2>/dev/null)" >&2
    done
    # Runtime power state of the remaining topology. If the camera link was
    # suspended at the moment it died, that is the single most useful fact we
    # can record -- and today it is invisible, because the device node is gone
    # by the time anyone inspects it.
    for d in "$SYSFS_USB"/*; do
        [ -d "$d/power" ] || continue
        printf '[camera-usb] usb-evidence: %s control=%s status=%s\n' \
            "${d##*/}" \
            "$(cat "$d/power/control" 2>/dev/null)" \
            "$(cat "$d/power/runtime_status" 2>/dev/null)" >&2
    done
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
# Issue #358: cached camera-state tuple so the line is emitted on change only.
last_reported_state=""
last_usb_present=-1
last_restarted=-1
last_state_identity="unset"
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
retry_after_poll=0
# Issue #347: last non-empty identity we ever saw, how many consecutive polls it
# has been absent, and whether this episode has already been announced. Seeded
# from the boot baseline: a camera present at launch is already "seen" before the
# first poll, and the startup-grace branch below `continue`s without ever running
# the tracking block -- so seeding here is what lets a loss during the grace
# window be reported at all.
last_seen_identity=$baseline
absent_polls=0
absent_announced=0
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
    [ "$USB_PIN_POWER" = "1" ] && pin_camera_power
    polls=$((polls + 1))

    # Issue #347: record a camera that disappeared and stayed gone. Deliberately
    # placed BEFORE the startup-grace branch, which `continue`s: without this, a
    # body lost during the grace window -- exactly when a slew at boot can drop it
    # -- would never be counted. Keyed on `current` being empty rather than on the
    # baseline, so it fires whether the loss was absorbed by grace, adopted as
    # healthy, or is sitting pending a restart.
    if [ -n "$current" ]; then
        if [ "$absent_announced" = "1" ]; then
            echo "[camera-usb] camera_returned: ${current} after $absent_polls absent polls (poll $polls)"
        fi
        last_seen_identity=$current
        absent_polls=0
        absent_announced=0
    elif [ -n "$last_seen_identity" ]; then
        absent_polls=$((absent_polls + 1))
        if [ "$ABSENT_ANNOUNCE_POLLS" -gt 0 ] \
           && [ "$absent_polls" -ge "$ABSENT_ANNOUNCE_POLLS" ] \
           && [ "$absent_announced" = "0" ]; then
            echo "[camera-usb] camera_absent: ${last_seen_identity} has not re-enumerated for $absent_polls polls (poll $polls); pgphoto has no device to bind and will not recover on its own -- power-cycle or replug the body (issue #347)" >&2
            [ "$ABSENT_EVIDENCE" = "1" ] && dump_usb_evidence "$last_seen_identity"
            absent_announced=1
        fi
    fi

    # Issue #358: report the four camera states separately. Placed here, before
    # the startup-grace branch below, for the same reason the #347 block is: that
    # branch `continue`s, so anything after it never runs during the grace window
    # -- which is precisely when a boot-time slew can drop a body. A restart that
    # happened on the previous poll is picked up here on this one.
    report_camera_state "$current"

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
        if [ "$qstable" -ge "$REBIND_STABLE_POLLS" ] && [ "$polls" -ge "$retry_after_poll" ]; then
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
                retry_after_poll=0
            else
                echo "[camera-usb] quarantined identity ${qcandidate:-none} stable for $qstable polls but bounded rebind failed; remaining degraded (issue #119)" >&2
                # Stay quarantined. Hold qstable at the threshold so the next poll
                # that keeps the identity stable immediately retries the rebind,
                # while any identity change resets qstable to 1 and re-arms it.
                qstable=$REBIND_STABLE_POLLS
                retry_after_poll=$((polls + RESTART_RETRY_POLLS))
                echo "[camera-usb] rebind retry deferred until poll $retry_after_poll" >&2
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

        if [ "$stable" -ge "$COOLDOWN" ] && [ "$polls" -ge "$retry_after_poll" ]; then
            if [ -z "$candidate" ]; then
                # Issue #358: the body is gone and has stayed gone. Restarting
                # pgphoto here cannot help -- there is no device for the new
                # process to bind, so it comes back with no camera and the
                # supervisor says so. Reproduced deterministically against a fake
                # sysfs: unplug a baselined body and the supervisor logs
                # "stable identity change: <id> -> none; restarting pgphoto" and
                # burns one of the MAX_RESTARTS slots on a restart that provably
                # binds nothing. When the body returns, baseline is now "none", so
                # a SECOND restart fires -- two full dlopen + 64-shim cycles for
                # one unplug/replug, against a budget of six.
                #
                # So do not restart while absent, but DO record absence as the
                # known state by clearing the baseline. That is the part that
                # matters: keeping the old identity here would make a same-address
                # reconnect look unchanged (current == baseline) and skip the
                # restart entirely, leaving pgphoto holding an fd to a device node
                # the kernel already invalidated. Clearing the baseline means any
                # return -- same or different address -- is seen as a change and
                # gets exactly one restart. Net effect: two restarts per unplug/
                # replug become one, and the budget is no longer spent on a no-op.
                #
                # The operator-visible signal for this state is the #347
                # camera_absent line above, which fires independently of here.
                if [ -n "$baseline" ]; then
                    echo "[camera-usb] body absent; not restarting pgphoto (nothing to bind) -- awaiting reconnection of ${baseline} (issue #358)"
                fi
                baseline=""
                candidate=""
                stable=0
                retry_after_poll=0
            elif [ -z "$baseline" ] && already_bound_k3iii "$candidate"; then
                echo "[camera-usb] adopting active pgphoto binding: $candidate"
                baseline=$candidate
                stable=0
                retry_after_poll=0
            elif [ "$MAX_RESTARTS" -gt 0 ] && [ "$restarts" -ge "$MAX_RESTARTS" ]; then
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
                    retry_after_poll=0
                    echo "[camera-usb] pgphoto restart complete (restart $restarts${MAX_RESTARTS:+/$MAX_RESTARTS})"
                else
                    # A competing watchdog/app restart may hold restart_gphoto's
                    # lock exactly when USB identity changes (observed on device:
                    # helper returned "another restart owns ... lock"). Keep the
                    # previous baseline so this identity remains pending, but back
                    # off before retrying; do not silently call it healthy.
                    restarts=$((restarts + 1))
                    stable=$COOLDOWN
                    retry_after_poll=$((polls + RESTART_RETRY_POLLS))
                    echo "[camera-usb] pgphoto restart failed; identity remains pending; retry deferred until poll $retry_after_poll" >&2
                fi
            fi
        fi
    fi

    [ "$MAX_POLLS" -gt 0 ] && [ "$polls" -ge "$MAX_POLLS" ] && exit 0
done
