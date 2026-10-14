#!/usr/bin/env bash
# o-v17a-autonomous-install.sh — wake Polaris via BT, stage o-v17a FwPkt to SD,
# reboot via 812, and verify the install (FwVer .66 + provenance).
#
# Designed to be run by an agent session that may not have the device reachable
# yet: every phase is idempotent and re-runnable. Run with --poll to keep
# retrying the wake phase until the device answers.
#
# Phases:
#   1. WAKE    — bluetoothctl connect $BT_MAC (if /dev/hci0 exists), then wait
#                for the polaris_* AP + SSH at $GIMBAL_HOST.
#   2. STAGE   — scp FwPkt.zip -> /app/sd/FwPkt.zip, verify md5 on-device.
#   3. REBOOT  — fire protocol code 812 (SYS_REBOOT) so the on-boot FwPkt
#                watcher installs from /app/sd/.
#   4. VERIFY  — wait for SSH, read /app/FwVer + provenance, print verdict.
#
# Env:
#   BT_MAC        (default 48:E7:DA:D4:B5:72)
#   GIMBAL_HOST   (default 192.168.0.1)
#   GIMBAL_PORT   (default 9090, wire protocol port for 812)
#   GIMBAL_SSH    (default root@<GIMBAL_HOST>)
#   FWPKT_ZIP     (default out/staged/o-v17a-shutter-fallback-off-20261012/FwPkt.zip)
#   EXPECTED_MD5  (auto-computed from FWPKT_ZIP if unset)
#   MAX_WAIT      (default 900 s for the device to come back after reboot)
#   POLL_INTERVAL (default 30 s between wake attempts in --poll mode)
#   POLL_LIMIT    (default 120 attempts in --poll mode)

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

BT_MAC="${BT_MAC:-48:E7:DA:D4:B5:72}"
GIMBAL_HOST="${GIMBAL_HOST:-192.168.0.1}"
GIMBAL_PORT="${GIMBAL_PORT:-9090}"
GIMBAL_SSH="${GIMBAL_SSH:-root@${GIMBAL_HOST}}"
FWPKT_ZIP="${FWPKT_ZIP:-out/staged/o-v17a-shutter-fallback-off-20261012/FwPkt.zip}"
MAX_WAIT="${MAX_WAIT:-900}"
POLL_INTERVAL="${POLL_INTERVAL:-30}"
POLL_LIMIT="${POLL_LIMIT:-120}"
WIRE='1&812&0&#'
SSH_OPTS="-o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes"

[ -f "$FWPKT_ZIP" ] || { echo "ERROR: FWPKT_ZIP not found: $FWPKT_ZIP"; exit 1; }
EXPECTED_MD5="${EXPECTED_MD5:-$(md5sum "$FWPKT_ZIP" | cut -d' ' -f1)}"

log() { echo "[o-v17a-install $(date +%H:%M:%S)] $*"; }

ssh_dev() { ssh $SSH_OPTS "$GIMBAL_SSH" "$@" 2>/dev/null; }

tcp_open() { (exec 3<>"/dev/tcp/${GIMBAL_HOST}/${GIMBAL_PORT}") 2>/dev/null && { exec 3>&-; return 0; } || return 1; }

phase_wake() {
  log "WAKE: attempting BT connect $BT_MAC"
  if [ -e /dev/hci0 ] && command -v bluetoothctl >/dev/null; then
    timeout 20 bluetoothctl --timeout 15 connect "$BT_MAC" >/dev/null 2>&1 \
      && log "WAKE: BT connect returned OK" || log "WAKE: BT connect failed/timed out (may still have woken it)"
  else
    log "WAKE: no /dev/hci0 or bluetoothctl — relying on AP/SSH already up"
  fi
  # Wait for the device to come up on the AP + SSH.
  local i
  for i in $(seq 1 24); do   # 24 x 5 s = 120 s
    if tcp_open && ssh_dev "true"; then
      log "WAKE: device reachable (TCP $GIMBAL_PORT + SSH)"
      return 0
    fi
    sleep 5
  done
  return 1
}

phase_stage() {
  log "STAGE: pushing FwPkt.zip ($(du -h "$FWPKT_ZIP" | cut -f1)) -> /app/sd/FwPkt.zip"
  scp $SSH_OPTS "$FWPKT_ZIP" "$GIMBAL_SSH:/app/sd/FwPkt.zip" >/dev/null 2>&1 \
    || { log "STAGE: scp failed"; return 1; }
  local actual
  actual="$(ssh_dev "md5sum /app/sd/FwPkt.zip 2>/dev/null | cut -d' ' -f1")"
  if [ "$actual" = "$EXPECTED_MD5" ]; then
    log "STAGE: on-device md5 matches ($EXPECTED_MD5)"
    return 0
  fi
  log "STAGE: md5 mismatch (device=$actual expected=$EXPECTED_MD5)"
  return 1
}

phase_reboot() {
  log "REBOOT: firing 812 (SYS_REBOOT) so the on-boot FwPkt watcher installs"
  printf '%s' "$WIRE" | timeout 10 nc "$GIMBAL_HOST" "$GIMBAL_PORT" >/dev/null 2>&1 \
    || log "REBOOT: 812 send failed (device may already be rebooting)"
  return 0
}

phase_verify() {
  log "VERIFY: waiting up to ${MAX_WAIT}s for the device to come back"
  local i
  for i in $(seq 1 $((MAX_WAIT / 15))); do
    if ssh_dev "true"; then break; fi
    sleep 15
  done
  ssh_dev "true" || { log "VERIFY: SSH still down after ${MAX_WAIT}s"; return 1; }
  sleep 30   # let polestar_app settle + getFwInfo run
  local fwver provenance
  fwver="$(ssh_dev "cat /app/FwVer 2>/dev/null")"
  log "VERIFY: /app/FwVer = ${fwver:-<unreadable>}"
  case "$fwver" in
    *6.0.0.54.66*) log "VERIFY: FwVer .66 PRESENT ✓";;
    *) log "VERIFY: FwVer .66 NOT found — install may not have completed"; return 1;;
  esac
  provenance="$(ssh_dev "grep -h . /app/stage2-provenance* /app/.polaris_build_id 2>/dev/null | head -3")"
  [ -n "$provenance" ] && log "VERIFY: provenance: $provenance"
  log "VERDICT: o-v17a install verified (FwVer 6.0.0.54.66)"
  return 0
}

case "${1:-}" in
  --poll)
    log "POLL mode: retrying wake every ${POLL_INTERVAL}s up to ${POLL_LIMIT} attempts"
    n=0
    while [ $n -lt "$POLL_LIMIT" ]; do
      n=$((n+1))
      if phase_wake; then
        phase_stage && phase_reboot && phase_verify \
          && { log "DONE: full autonomous install complete"; exit 0; }
        # Device went dark after reboot — re-wake and continue.
        sleep "$POLL_INTERVAL"
      else
        sleep "$POLL_INTERVAL"
      fi
    done
    log "POLL mode: exhausted ${POLL_LIMIT} attempts"
    exit 2
    ;;
  *)
    phase_wake   || { log "device not reachable — re-run with --poll or wake manually"; exit 3; }
    phase_stage  || exit 4
    phase_reboot
    phase_verify || exit 5
    log "DONE: full autonomous install complete"
    ;;
esac
