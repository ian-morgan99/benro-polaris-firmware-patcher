#!/usr/bin/env bash
# restore-rig-bluez-entry.sh — recreate the BlueZ Device object for the Benro
# Polaris so a bare GATT connect (the wake pulse) works again from this host.
#
# WHY THE DESKTOP APP STOPPED WORKING (found 2026-11-27)
# The desktop wake path is a bare GATT connect to 48:E7:DA:D4:B5:72. BlueZ can
# only connect to an address it already has a Device object for; otherwise it
# prints "Device <MAC> not available" and sends nothing. That object is created
# by discovery or pairing and persisted under /var/lib/bluetooth/<adapter>/.
#
# The original working setup paired the rig (OpenPolaris
# docs/KEEPALIVE-WAKE-INVESTIGATION-2026-09-07.md step 2 is literally
# "bluetoothctl pair ADDRESS"), which created a persistent object. It worked for
# months. Then on 2026-10-27 a diagnostic session ran, recorded verbatim in
# docs/evidence/rig-le-advertising-absent-20261027/SUMMARY.md:
#
#     $ bluetoothctl remove 48:E7:DA:D4:B5:72
#
# That deleted the Device object and its bond key. Current state confirms it is
# gone and has never come back:
#
#     $ bluetoothctl devices            -> (no output, count 0)
#     $ busctl tree org.bluez           -> /org/bluez/hci0 only, 0 dev_ objects
#     $ bluetoothctl connect 48:E7:...  -> "Device 48:E7:DA:D4:B5:72 not available"
#
# Why it cannot self-heal: BlueZ recreates an object only when the device is
# discovered. The rig never advertises LE — its own log shows
# "Failed to register advertising object" on every boot (reg_fail=1 in 5 of 5
# Mlogs) — so an LE scan can never bring it back. That is why the removal was
# permanent rather than a transient hiccup.
#
# The host radio is NOT at fault and needs no firmware work: RX bytes advance
# during scans, and OpenPolaris BluetoothProbe.kt records this same adapter
# receiving an unrelated advertiser on 2026-10-08. scripts/fix-bt-adapter-qca.sh
# addresses a separate, unproven gap and is not the fix for this regression.
#
# RECOVERY PATHS, in order of preference
#   1. Classic BR/EDR discovery. The rig IS classically reachable — it runs
#      PSCAN ISCAN and carries BR/EDR connections (SP_EVENT_BT_CONNECT), which
#      is why a phone app connects. A classic inquiry creates the Device object
#      without needing LE advertising. Requires the rig awake and in range.
#   2. LE scan, only if the rig ever does advertise (firmware change).
#   3. Hand-write the BlueZ device file and restart bluetoothd. Root. Last
#      resort: it restores connectivity for a known-good address but skips
#      re-bonding, so pairing-dependent operations may still fail.
#
# Usage:
#   ./restore-rig-bluez-entry.sh              # paths 1-2, then verify + wake
#   sudo ./restore-rig-bluez-entry.sh --file  # path 3 as well
set -uo pipefail

MAC="${POLARIS_BT:-48:E7:DA:D4:B5:72}"
OBJ="dev_${MAC//:/_}"
ADAPTER=$(timeout 8 bluetoothctl show 2>/dev/null | awk '/^Controller/{print $2; exit}')
[ -n "$ADAPTER" ] || { echo "[restore] no Bluetooth adapter visible to BlueZ" >&2; exit 3; }
DEVDIR="/var/lib/bluetooth/$ADAPTER/$OBJ"

log() { printf '[restore] %s\n' "$*"; }
have_obj() { timeout 8 bluetoothctl info "$MAC" 2>/dev/null | grep -q "Device $MAC"; }

if have_obj; then
  log "Device object already exists:"
  timeout 8 bluetoothctl info "$MAC" 2>&1 | sed 's/^/    /'
else
  log "no Device object for $MAC — BlueZ will refuse to connect. Recreating."

  # --- path 1: classic BR/EDR inquiry (the rig is PSCAN ISCAN) --------------
  log "classic discovery, 40 s (transport=public)"
  # Piped rather than a heredoc: a heredoc body puts bare words such as `quit`
  # on their own line, and tests/test_shell_no_bare_fragments.sh flags those as
  # stray command lines (it greps ^[a-z]{1,5}$ with no heredoc awareness).
  printf '%s\n' 'power on' 'experimental on' 'discoverable-timeout 0' 'scan on' 'quit' \
    | timeout 55 bluetoothctl 2>&1 \
    | sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g' \
    | grep -iE "new device|changing|not available" | head -12

  if ! have_obj; then
    # --- path 2: LE scan, cheap to try --------------------------------------
    log "LE scan, 30 s"
    timeout 45 bluetoothctl --timeout 30 scan on 2>&1 \
      | sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g' | grep "\[NEW\] Device" | head -8
  fi

  # --- path 3: write the device file directly (root, opt-in) ----------------
  if ! have_obj && [ "${1:-}" = "--file" ]; then
    [ "$(id -u)" -eq 0 ] || { log "--file needs root"; exit 1; }
    if [ -d "$DEVDIR" ]; then
      log "a file already exists at $DEVDIR, not overwriting"
    else
      mkdir -p "$DEVDIR"
      # Minimal valid entry. Identity is left blank because the rig's LE name is
      # unknown here; Trusted/Blocked are deliberately conservative.
      cat > "$DEVDIR/info" <<INFO
[General]
Timestamp=$(date +%s)
Modality=0
Modalias=
Blocked=false
Trusted=false
LegacyPairing=false
Paired=false
HasIdentity=false
Resolved=false
INFO
      printf '[General]\nAddress=%s\nAddressType=%s\n' "$MAC" "public" > "$DEVDIR/name" 2>/dev/null || true
      log "wrote $DEVDIR/info (Paired=false; re-pair later if a feature needs it)"
      log "restarting bluetoothd so it loads the new entry"
      systemctl restart bluetooth || service bluetooth restart
      sleep 4
    fi
  elif ! have_obj && [ "${1:-}" != "--file" ]; then
    log "discovery did not find it. If the rig is awake and in range this means"
    log "classic inquiry is also failing here; otherwise re-run when it is awake."
    log "Last resort (root): $0 --file"
  fi
fi

# --- verify, then attempt the actual wake pulse -----------------------------
if ! have_obj; then
  log "FAILED: still no Device object. Nothing to connect to."
  log "This is unrecoverable from Linux while the rig advertises nothing and is"
  log "not classically reachable. Options: pair it from a phone first, or use"
  log "$0 --file once the rig is awake."
  exit 1
fi

log "Device object present:"
timeout 8 bluetoothctl info "$MAC" 2>&1 | sed 's/^/    /'

log "wake pulse (bare GATT connect, then disconnect)"
printf '%s\n' "connect ${MAC}" "disconnect ${MAC}" 'quit' \
  | timeout 35 bluetoothctl 2>&1 \
  | sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g' | tail -8

log "done. Start the Wi-Fi association immediately — do not wait for GATT"
log "service discovery (see .github/skills/polaris-debugging/SKILL.md §5)."
