#!/usr/bin/env bash
# Polaris BT keepalive — holds an independent Bluetooth link to the Polaris so
# that if Wi-Fi/SSH drops (e.g. #55 radio starvation during liveview), we still
# have a wake/reach path and don't lose hours waiting for a manual power-on.
set -u
BT_MAC="48:E7:DA:D4:B5:72"
SSH_HOST="root@192.168.0.1"
LOG="/tmp/polaris-bt-keepalive.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== Polaris BT keepalive started (pid $$) ==="
while true; do
  if bluetoothctl info "$BT_MAC" 2>/dev/null | grep -q "Connected: yes"; then
    if timeout 6 ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" 'uptime' >/dev/null 2>&1; then
      log "BT connected + SSH up"
    else
      log "BT connected but SSH down (possible radio starvation)"
    fi
    sleep 30
  else
    bluetoothctl scan on >/dev/null 2>&1
    sleep 8
    bluetoothctl scan off >/dev/null 2>&1
    if timeout 15 bluetoothctl --timeout 12 connect "$BT_MAC" >/dev/null 2>&1; then
      log "BT reconnected to $BT_MAC"
    else
      log "BT not reachable (device off / out of range)"
    fi
    sleep 20
  fi
done
