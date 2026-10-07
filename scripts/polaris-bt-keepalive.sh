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
#   - wake when down: the canonical double ping (connect -> verify the link is
#     actually HELD -> disconnect), then immediate association with the saved
#     profile, polling for the AP by SSID/BSSID.
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

protocol_ping() {
  printf '1&266&0&#' | timeout 4 nc -q1 192.168.0.1 9090 >/dev/null 2>&1
}

control_up() { protocol_ping; }

bt_advertising() {
  timeout 18 bluetoothctl --timeout 15 scan on 2>/dev/null | grep -qi "$BT_MAC"
}

# Returns 0 only if the GATT link is established AND still held 2 s later.
# This is the check v1 never did; without it every aborted link looks like a
# successful reconnect.
bt_connect_held() {
  timeout 20 bluetoothctl --timeout 15 connect "$BT_MAC" >/dev/null 2>&1
  sleep 2
  bluetoothctl info "$BT_MAC" 2>/dev/null | grep -q "Connected: yes"
}

bt_release() {
  timeout 10 bluetoothctl --timeout 8 disconnect "$BT_MAC" >/dev/null 2>&1
}

join_ap() {
  # Kick the saved profile immediately (the documented handoff starts
  # association during/after the pulse), then wait for the AP and activate.
  nmcli connection up "$AP_SSID" >/dev/null 2>&1 &
  local i
  for i in $(seq 1 "$AP_WAIT_POLLS"); do
    sleep 5
    if nmcli device wifi list --rescan yes 2>/dev/null | grep -qi "$AP_SSID"; then
      nmcli connection up "$AP_SSID" >/dev/null 2>&1 && return 0
    fi
  done
  return 1
}

wait_ssh() {
  local i
  for i in 1 2 3 4 5; do
    if timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=6 "$SSH_HOST" uptime >/dev/null 2>&1; then
      return 0
    fi
    sleep 4
  done
  return 1
}

log "=== Polaris keepalive v2 started (pid $$) ==="
while true; do
  if control_up; then
    log "phase=control-up; holding with 9090 protocol ping every ${PING_INTERVAL}s"
    for _ in $(seq 1 "$CONTROL_WINDOW"); do
      sleep "$PING_INTERVAL"
      protocol_ping
    done
  else
    log "phase=no-control; attempting wake"
    if ! bt_advertising; then
      log "phase=not-advertising; rig is below wakeable state (hard-off/deep sleep) - physical wake required"
      sleep "$NOT_ADV_SLEEP"
      continue
    fi
    if ! bt_connect_held; then
      log "phase=connect-aborted; link does not hold (check RSSI/position) - not claiming wake"
      sleep "$DOWN_SLEEP"
      continue
    fi
    bt_release
    log "phase=gatt-pulse-delivered; associating"
    if join_ap; then
      if wait_ssh; then
        log "phase=ssh-up; wake succeeded"
      else
        log "phase=joined-ssh-down; associated but daemon not answering yet"
      fi
    else
      log "phase=ap-not-visible; wake pulse did not bring up the AP"
    fi
    sleep "$DOWN_SLEEP"
  fi
done
