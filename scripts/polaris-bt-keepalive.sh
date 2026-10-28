#!/usr/bin/env bash
# Polaris keepalive + wake, v2.
#
# v1 (2026-09) held a bare `bluetoothctl connect` and logged "BT reconnected"
# whenever the connect CALL returned -- but BlueZ resolves asynchronously, the
# link aborts locally (le-connection-abort-by-local) ~1 s later, and the log
# lied (OpenPolaris issue #97 documents the same defect in the Kotlin path).
# v1 also used the deprecated pair-first wake form.
#
# v2 implements the documented protocol honestly:
#   - keep-awake while connected: the protocol ping `1&266&0&#` on TCP 9090
#     every 30 s (the firmware AP idle timer is ~5 min of no 9090 traffic;
#     284/822 polling does NOT reset it - KEEPALIVE-WAKE-INVESTIGATION-2026-09-07).
#   - wake when down: the canonical pulse (connect -> verify the link is
#     actually HELD), then immediate association with the saved profile,
#     polling for the AP by SSID/BSSID.
#   - HOLD like the vendor app: Benro Connect keeps GATT open for the whole
#     session (this is what resets the firmware's ~90 s AP watchdog; see
#     OpenPolaris 0a1cbaf + KEEPALIVE-WAKE-INVESTIGATION-2026-09-07). v2.1
#     therefore RETAINS the verified GATT link through the Wi-Fi handoff and
#     re-establishes it if it drops while we own the control session; it is
#     released only when we give up control (EXIT trap).
#   - every outcome is logged as a terminal PHASE, never as a vague success:
#       control-up | not-advertising | connect-aborted | ap-not-visible |
#       joined-ssh-down | ssh-up
#     "not-advertising" means the rig is below the wakeable state (hard-off /
#     deep sleep) - no host-side sequence can fix that; it needs a physical
#     wake (see polaris-debugging skill §5).
set -u

BT_MAC="${OPENPOLARIS_BT_MAC:-48:E7:DA:D4:B5:72}"
AP_SSID="${OPENPOLARIS_AP_SSID:-polaris_d13e86}"
SSH_HOST="${OPENPOLARIS_SSH:-root@192.168.0.1}"
LOG="/tmp/polaris-bt-keepalive.log"
PING_INTERVAL=30          # protocol-ping cadence while in control-up
CONTROL_WINDOW=10         # pings per control-up window before re-checking
AP_WAIT_POLLS=12          # 12 x 5 s = 60 s AP wait (skill default)
DOWN_SLEEP=30             # backoff after a failed wake phase
NOT_ADV_SLEEP=60          # backoff while the rig is not advertising at all

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# ---------------------------------------------------------------------------
# Host routing + Bluetooth reachability (see scripts/polaris-bt-probe.sh).
# Inside the VS Code Flatpak, bluetoothctl/nmcli/ssh are absent and /dev/hci0
# does not exist even though the host has them all. Before this module existed
# this daemon silently concluded "rig is below wakeable state (hard-off/deep
# sleep)" from an empty scan that proved nothing -- the greps never matched
# bluetoothctl's real `[NEW] Device` output and the portal PTY colourises it.
# See docs/evidence/rig-le-advertising-absent-20261027/SUMMARY.md.
# ---------------------------------------------------------------------------
BT_PROBE_LIB="$(cd "$(dirname "$0")" && pwd)/polaris-bt-probe.sh"
if [ -r "$BT_PROBE_LIB" ]; then
  # shellcheck source=./polaris-bt-probe.sh
  . "$BT_PROBE_LIB"
else
  BT_ROUTE="none"; BT_CMD=()
  bt_resolve() { return 2; }
  bt_timeout() { return 127; }
  bt_exec() { return 127; }
  bt_bin_timeout() { return 127; }
  bt_acl_counter() { :; }
  bt_radio_liveness() { BT_LIVENESS_DETAIL="probe module missing"; return 3; }
fi
HOST_PREFIX=()
if ! command -v nmcli >/dev/null 2>&1 && command -v flatpak-spawn >/dev/null 2>&1 \
   && ( cd "$PWD" && timeout 10 flatpak-spawn --host nmcli --version ) >/dev/null 2>&1; then
  HOST_PREFIX=(flatpak-spawn --host)
fi
# run_host [OPTIONS] <cmd>... -- run a host command on the resolved route.
#   run_host --timeout SECS cmd...  applies the deadline to the real binary.
# `timeout N run_host ...` CANNOT work: timeout execs a binary and cannot invoke
# a shell function, so it silently fails and wait_ssh() always returned failure.
run_host() {
  if [ "${1:-}" = "--timeout" ]; then
    local t="$2"; shift 2
    if [ "${#HOST_PREFIX[@]}" -gt 0 ]; then
      ( cd "$PWD" && timeout "$t" "${HOST_PREFIX[@]}" "$@" )
    else
      timeout "$t" "$@"
    fi
  elif [ "${#HOST_PREFIX[@]}" -gt 0 ]; then
    ( cd "$PWD" && "${HOST_PREFIX[@]}" "$@" )
  else
    "$@"
  fi
}

protocol_ping() {
  printf '1&266&0&#' | timeout 4 nc -q1 192.168.0.1 9090 >/dev/null 2>&1
}

control_up() { protocol_ping; }

bt_advertising() {
  [ "$BT_ROUTE" = local ] || [ "$BT_ROUTE" = portal ] || return 2
  bt_timeout 18 --timeout 15 scan on 2>/dev/null | grep -qi "$BT_MAC"
}

# Returns 0 only if the GATT link is established AND still held 2 s later.
# This is the check v1 never did; without it every aborted link looks like a
# successful reconnect.
bt_connect_held() {
  bt_timeout 20 --timeout 15 connect "$BT_MAC" >/dev/null 2>&1
  sleep 2
  bt_timeout 10 info "$BT_MAC" 2>/dev/null | grep -q "Connected: yes"
}

bt_release() {
  bt_timeout 10 --timeout 8 disconnect "$BT_MAC" >/dev/null 2>&1
}

bt_held() {
  bt_timeout 10 info "$BT_MAC" 2>/dev/null | grep -q "Connected: yes"
}

# Vendor-algorithm hold: while we own the control session, GATT must stay up.
# Re-pulse (connect only, no disconnect) if the link dropped. Bounded: one
# attempt per keepalive cycle; failures are logged, never fatal.
bt_ensure_held() {
  if bt_held; then
    return 0
  fi
  log "phase=gatt-dropped; re-pulsing to restore hold"
  bt_timeout 20 --timeout 15 connect "$BT_MAC" >/dev/null 2>&1
  sleep 2
  if bt_held; then
    log "phase=gatt-held"
    return 0
  fi
  log "phase=gatt-hold-failed; continuing on Wi-Fi keepalive alone"
  return 1
}

join_ap() {
  # Kick the saved profile immediately (the documented handoff starts
  # association during/after the pulse), then wait for the AP and activate.
  run_host nmcli connection up "$AP_SSID" >/dev/null 2>&1 &
  local i
  for i in $(seq 1 "$AP_WAIT_POLLS"); do
    sleep 5
    if run_host nmcli device wifi list --rescan yes 2>/dev/null | grep -qi "$AP_SSID"; then
      run_host nmcli connection up "$AP_SSID" >/dev/null 2>&1 && return 0
    fi
  done
  return 1
}

wait_ssh() {
  local i
  for i in 1 2 3 4 5; do
    if run_host --timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=6 "$SSH_HOST" uptime >/dev/null 2>&1; then
      return 0
    fi
    sleep 4
  done
  return 1
}

trap 'bt_release; log "phase=exit; GATT released, control owner gone"' EXIT

log "=== Polaris keepalive v2.2 started (pid $$) ==="
# Report what we can actually verify at startup, rather than looping on a scan
# whose result is uninformative. Without this the daemon spins in
# phase=not-advertising forever and the log reads as though the gimbal is
# permanently asleep.
bt_resolve || true
log "phase=startup; bluetoothctl route=$BT_ROUTE host-tools=${HOST_PREFIX[0]:-local}"
case "$BT_ROUTE" in
  local|portal) :
    rc=0; bt_radio_liveness 15 || rc=$?
    if [ "$rc" -eq 0 ]; then
      log "phase=radio-alive; ${BT_LIVENESS_DETAIL:-}"
    else
      case "$rc" in
        1) log "phase=liveness-unknown; ${BT_LIVENESS_DETAIL:-} - empty scan proves nothing (rig LE advertising is unreliable, BlueZ caches devices). Not evidence of a dead radio.";;
        2) log "phase=no-adapter; bluetoothctl unreachable (route=$BT_ROUTE); Wi-Fi keepalive only, wake is impossible from here.";;
        *) log "phase=radio-unprobeable; cannot probe host radio (${BT_LIVENESS_DETAIL:-}); wake may be unavailable";;
      esac
    fi;;
  *) log "phase=no-adapter; bluetoothctl unreachable (route=$BT_ROUTE). Wi-Fi keepalive only; wake is impossible from here.";;
esac
while true; do
  if control_up; then
    log "phase=control-up; holding with 9090 protocol ping every ${PING_INTERVAL}s"
    for _ in $(seq 1 "$CONTROL_WINDOW"); do
      sleep "$PING_INTERVAL"
      protocol_ping
      bt_ensure_held
    done
  else
    log "phase=no-control; attempting wake"
    if ! bt_advertising; then
      # An empty scan proves nothing: the rig does not reliably advertise LE
      # (Mlog logs "Failed to register advertising object" on every boot) and
      # bluetoothctl emits `[NEW] Device` only once per cached device. Report
      # why we cannot tell, and never assert the rig is asleep from this alone.
      rc=0; bt_radio_liveness 15 || rc=$?
      case "$rc" in
        0) log "phase=not-advertising; host radio does receive (${BT_LIVENESS_DETAIL:-}) so the rig is genuinely not advertising LE - note it may still be awake but advertising-disabled";;
        1) log "phase=scan-empty-inconclusive; ${BT_LIVENESS_DETAIL:-} - empty scan proves nothing (rig LE advertising is unreliable; BlueZ caches devices). Cannot distinguish deaf radio from sleeping rig. Backing off.";;
        2) log "phase=no-adapter; bluetoothctl unreachable mid-run (route=$BT_ROUTE); backing off";;
        *) log "phase=radio-unprobeable; cannot probe host radio (${BT_LIVENESS_DETAIL:-}); backing off";;
      esac
      sleep "$NOT_ADV_SLEEP"
      continue
    fi
    if ! bt_connect_held; then
      log "phase=connect-aborted; link does not hold (check RSSI/position) - not claiming wake"
      sleep "$DOWN_SLEEP"
      continue
    fi
    # NOTE: no bt_release here. Like Benro Connect, we RETAIN the verified GATT
    # link through the Wi-Fi handoff; it is what holds the AP past the ~90 s
    # watchdog. It is released only on exit (trap below).
    log "phase=gatt-pulse-delivered-held; associating"
    if join_ap; then
      if wait_ssh; then
        log "phase=ssh-up; wake succeeded (GATT retained)"
      else
        log "phase=joined-ssh-down; associated but daemon not answering yet"
      fi
    else
      log "phase=ap-not-visible; wake pulse did not bring up the AP"
      bt_release
    fi
    sleep "$DOWN_SLEEP"
  fi
done
