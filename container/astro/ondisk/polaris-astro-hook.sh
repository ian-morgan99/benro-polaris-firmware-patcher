#!/bin/sh
# ============================================================================
#  /app boot hook that starts the Astro stack from the microSD card.
#
#  WHY THIS FILE EXISTS (#265)
#  ---------------------------
#  The Astro bundle ships polaris-astro-boot.sh, which is complete and correct:
#  it waits for the card, syncs the bundle into /app/astro and starts
#  polaris-httpd. On 6.0.0.54.101 (build_id v101) it was never invoked by
#  anything. Measured on-device:
#
#      ls -d /app/astro                       -> DOES NOT EXIST
#      [ -x /app/sd/polaris-astro/polaris-astro-boot.sh ] -> yes
#      grep -rl "polaris-astro\|astro-boot" /etc /app/etc /init.d -> (nothing)
#      ps | grep polaris-httpd                -> none running
#
#  The init chain is /etc/init.d/rcS, which runs only S00devs, S10mpp and
#  S80network; there is no rc.local. S10mpp runs /app/bootapp, and bootapp calls
#  exactly two optional hooks:
#
#      if [ -f "/app/network_telnetd.sh" ];then cd /app; ./network_telnetd.sh; fi
#      if [ -f "/app/start_agent.sh" ];then    cd /app; ./start_agent.sh;    fi
#
#  The bundle's own installer, install_astro.sh, is what writes one of those
#  hooks -- but install_astro.sh has to be run by hand, so on a fresh install
#  nothing ever calls it and the whole stack stays unreachable no matter how
#  correct the bundle is. This file closes that gap: the patcher installs it at
#  flash time, so the card's boot script runs at boot without any manual step.
#
#  IT MUST NOT BLOCK. bootapp runs hooks inline, before anything else finishes
#  coming up. Everything slow is backgrounded and every wait is bounded, so a
#  missing or dead card cannot stall boot.
#
#  IT MUST NOT TAKE OVER THE SSH HOOK. /app/network_telnetd.sh is one slot and
#  the patcher's --ssh-key option (#31) writes the same file. If this launcher
#  lands on a slot that already holds another hook, the patcher moves that hook
#  to /app/<name>.pre-astro.sh and we run it FIRST, before touching astro, so
#  ssh comes up even if everything below fails. Losing it would lock us out of
#  the device we are debugging.
# ============================================================================

# SD_ROOT and APP_ROOT are overridable so the pre-release gate can exercise every
# path (no card, card without the boot script, card with it, and the ssh-chaining
# path) against a temp directory instead of needing a flashed device. The chaining
# path is the one that decides whether a user keeps ssh, so it must not be testable
# only on hardware. Defaults are the real paths.
SD_ROOT=${SD_ROOT:-/app/sd}
APP_ROOT=${APP_ROOT:-/app}
CARD_DIR="$SD_ROOT/polaris-astro"
CARD_BOOT="$CARD_DIR/polaris-astro-boot.sh"
SELF=$(basename "$0")
LOG="$CARD_DIR/boot-hook.log"

log() {
    # The card may not be mounted yet, so fall back to the appfs log rather
    # than dropping the message -- a silent failure is the bug being fixed.
    if [ -d "$CARD_DIR" ]; then
        echo "$(date) [astro-hook] $*" >> "$LOG" 2>/dev/null || true
    fi
    echo "[astro-hook] $*"
}

{
    log "boot hook started ($SELF)"

    # ---- chain any hook that was displaced from THIS slot -----------------
    # The patcher saves whatever previously occupied the slot as
    # /app/<name>.pre-astro.sh. Run it first: if astro fails, ssh must still
    # come up.
    #
    # Only the same-slot file is chained here. /app/network_telnetd.pre-astro.sh
    # is deliberately NOT chained, because the card's own boot script already
    # runs it (polaris-astro-boot.sh lines ~38-40) -- chaining it here too would
    # run the ssh setup twice on every boot.
    if [ -x "$APP_ROOT/$SELF.pre-astro.sh" ]; then
        log "chaining preserved hook $APP_ROOT/$SELF.pre-astro.sh"
        "$APP_ROOT/$SELF.pre-astro.sh" || log "  (it returned $?)"
    fi

    # ---- is the astro card here at all? ----------------------------------
    # Bounded wait: /app/sd is not mounted when bootapp starts. Detect the card
    # by the bundle directory rather than site.conf, because a fresh card has
    # the bundle but no config yet -- keying on config alone was how an earlier
    # version exited silently.
    #
    # ASTRO_CARD_WAIT is the number of 2 s polls. It is overridable so the gate
    # can exercise the no-card path in under a second instead of waiting out the
    # full boot allowance; the default is what ships.
    POLLS=${ASTRO_CARD_WAIT:-30}
    i=0
    while [ "$i" -lt "$POLLS" ]; do
        [ -d "$CARD_DIR" ] && break
        sleep 2
        i=$((i + 1))
    done

    if [ ! -d "$CARD_DIR" ]; then
        log "no $CARD_DIR after $((POLLS * 2))s; astro not started (nothing to do)"
        exit 0
    fi

    if [ ! -f "$CARD_BOOT" ]; then
        log "card is present but $CARD_BOOT is missing; cannot start astro"
        exit 0
    fi

    # ---- run the card's boot script --------------------------------------
    # It is the single source of truth: it syncs the bundle into /app/astro,
    # applies site.conf and starts polaris-httpd. Running it in the background
    # keeps this hook non-blocking for bootapp.
    log "starting $CARD_BOOT"
    setsid sh "$CARD_BOOT" </dev/null >/dev/null 2>&1 &
    log "launched (pid $!); astro web UI listens on :8090 when it is up"
} 2>&1

exit 0
