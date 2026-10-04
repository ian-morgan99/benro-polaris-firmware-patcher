#!/usr/bin/env bash
# polaris-preflight.sh — fail closed unless the host genuinely has a path to
# the gimbal, and say *why* when it does not.
#
# Why this exists. Two independent signals have repeatedly convinced us the
# device was present when it was not:
#
#   * 192.168.0.1 answers a ping and serves HTTP on port 80 — on the wired
#     side that is the home router, not the gimbal.
#   * `bluetoothctl devices` lists polaris_d13e86 from the bluez cache long
#     after the SoC has slept. The SoC, its AP and its BLE radio sleep
#     together, so a cached entry proves nothing about the present.
#
# A session started against either of those produces "the firmware broke the
# network" conclusions that were really a flat battery or a sleeping device.
# This script enforces the identity rule already written in AGENTS.md, and
# returns a specific reason instead of a bare ping failure.
#
# Checks, in order, each of which can end the run:
#   1. live BLE advertisement  (cache deliberately cleared first)
#   2. AP broadcasting under the gimbal's OUI
#   3. host associated to that AP on the Wi-Fi interface
#   4. route to the gimbal address via the Wi-Fi interface, not the LAN cable
#   5. control/SSH ports answering, then /app/FwVer actually readable
#
# Usage:
#   scripts/polaris-preflight.sh [options]
#
# Options:
#   --wake              send one BLE wake pulse and wait for the AP to appear
#   --keepalive         hold a 9090 status ping for the lifetime of this shell
#   --wait SECS         seconds to wait for the AP when --wake is given
#                       (default 0; use 300 after a reflash)
#   --scan SECS         BLE advertisement window (default 20)
#   --quiet             only print the final verdict line
#
# Exit codes (stable; safe to branch on):
#   0 READY            1 ASLEEP           2 WRONG_NETWORK
#   3 BOOTING          4 NO_SSH           5 HOST_TOOLING
set -uo pipefail

BT_MAC="${POLARIS_BT:-48:E7:DA:D4:B5:72}"
AP_OUI="${POLARIS_AP_OUI:-48:E7:DA}"
AP_SSID="${POLARIS_SSID:-polaris_d13e86}"
HOST="${POLARIS_HOST:-192.168.0.1}"
SSH_USER="${POLARIS_SSH_USER:-root}"
WIFI_IFACE="${WIFI_IFACE:-wlp8s0}"
SCAN_SECS=20
WAIT_AP_SECS=0
WAKE=0
KEEPALIVE=0
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --wake) WAKE=1; shift;;
    --keepalive) KEEPALIVE=1; shift;;
    --wait) WAIT_AP_SECS="$2"; shift 2;;
    --scan) SCAN_SECS="$2"; shift 2;;
    --quiet) QUIET=1; shift;;
    -h|--help) sed -n '2,40p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

say() { [ "$QUIET" = "1" ] || printf '%s\n' "$*"; }

VERDICT="UNKNOWN"
detail() { VERDICT="$1"; shift; printf 'VERDICT=%s' "$VERDICT"; printf ' %s' "$@"; printf '\n'; }

for tool in nmcli ip ssh; do
  command -v "$tool" >/dev/null 2>&1 || { detail HOST_TOOLING "missing=$tool"; exit 5; }
done
HAVE_BT=0
command -v bluetoothctl >/dev/null 2>&1 && HAVE_BT=1

ap_visible() {
  timeout 15 nmcli -t -f BSSID,SSID dev wifi list --rescan yes 2>/dev/null \
    | grep -i "$AP_OUI" | head -1
}

associated() {
  nmcli -t -f NAME,DEVICE,STATE connection show --active 2>/dev/null \
    | awk -F: -v s="$AP_SSID" '$1 ~ s || $1 ~ /^polaris_/' | head -1
}

# `bluetoothctl devices` keeps listing a device long after it has gone to
# sleep, so it cannot prove presence. A live advertisement, unlike a cached
# entry, always produces a "New Device" line during a scan window. Observed
# 2026-10-04: a 20 s scan produced no such line while `devices` still listed
# polaris_d13e86, and the device was in fact asleep.
#
# This deliberately does not call `bluetoothctl remove`: that would discard
# the stored Trusted flag as a side effect of a read-only check.
ble_advertising() {
  [ "$HAVE_BT" = "1" ] || return 2
  local out found=1
  out="$(mktemp)"
  timeout "$((SCAN_SECS + 5))" bluetoothctl --timeout "$SCAN_SECS" scan on >"$out" 2>&1
  grep -qi "New Device $BT_MAC" "$out" && found=0
  rm -f "$out"
  return "$found"
}

say "--- polaris preflight $(date -u +%FT%TZ) ---"

# 1. Live BLE advertisement. Absent with no AP, this is a sleeping or powered
#    off device, which is a different problem from a broken firmware image.
BLE=unknown
if [ "$HAVE_BT" = "1" ]; then
  say "[1/5] BLE advertisement (cache cleared, ${SCAN_SECS}s window)..."
  if ble_advertising; then BLE=yes; say "      live advertisement seen from $BT_MAC"
  else BLE=no; say "      no advertisement (cached entries ignored)"; fi
else
  say "[1/5] BLE skipped (no bluetoothctl)"
fi

AP="$(ap_visible)"
say "[2/5] AP broadcast..."
if [ -n "$AP" ]; then
  say "      visible: $AP"
else
  say "      not broadcasting"
  if [ "$WAKE" = "1" ]; then
    [ "$HAVE_BT" = "1" ] || { detail HOST_TOOLING "missing=bluetoothctl for --wake"; exit 5; }
    say "      sending BLE wake pulse, waiting up to ${WAIT_AP_SECS}s"
    timeout 25 bluetoothctl connect "$BT_MAC" >/dev/null 2>&1
    deadline=$(( $(date +%s) + WAIT_AP_SECS ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
      sleep 8
      AP="$(ap_visible)"
      [ -n "$AP" ] && { say "      visible after wait: $AP"; break; }
    done
  fi
fi

if [ -z "$AP" ]; then
  if [ "$BLE" = "no" ]; then
    detail ASLEEP "no BLE advertisement and no AP; the SoC is asleep or unpowered. Power-cycle it, or check the battery."
    exit 1
  fi
  detail BOOTING "BLE present but AP not broadcasting; the device is waking or hostapd is not up. Wait, or power-cycle."
  exit 3
fi

# 3. Association must be to the gimbal, on the Wi-Fi interface.
say "[3/5] association..."
ASSOC="$(associated)"
if [ -z "$ASSOC" ]; then
  say "      not associated; attempting join"
  if ! timeout 30 nmcli device wifi connect "$AP_SSID" >/dev/null 2>&1; then
    detail WRONG_NETWORK "cannot associate to $AP_SSID; the stored profile may be stale (PSK rotates on reflash)"
    exit 2
  fi
  ASSOC="$(associated)"
  [ -n "$ASSOC" ] || { detail WRONG_NETWORK "join reported success but no active polaris connection"; exit 2; }
fi
say "      $ASSOC"

# 4. The route must go out of the Wi-Fi interface. This is the check that
#    separates the gimbal from the home router sharing 192.168.0.1.
say "[4/5] route to $HOST..."
ROUTE="$(ip route get "$HOST" 2>/dev/null | head -1)"
say "      $ROUTE"
case "$ROUTE" in
  *"dev $WIFI_IFACE"*) :;;
  *)
    detail WRONG_NETWORK "route is not via $WIFI_IFACE; $HOST is being answered by another host (the LAN router shares this address)"
    exit 2
    ;;
esac

# 5. Ports, then the authoritative identity file. A ping or an open port 80 is
#    not enough: the router serves that too.
say "[5/5] services..."
port_open() { timeout 4 bash -c "echo > /dev/tcp/$HOST/$1" 2>/dev/null; }
SSH_OK=0
port_open 22 && SSH_OK=1
if [ "$SSH_OK" != "1" ]; then
  if port_open 80 || port_open 9090; then
    detail BOOTING "reachable but sshd not up yet; the device is still booting"
    exit 3
  fi
  detail NO_SSH "associated and routed correctly but no service answered on 22/80/9090"
  exit 4
fi

FWVER="$(timeout 20 ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
  "$SSH_USER@$HOST" 'cat /app/FwVer 2>/dev/null; echo; sed -n "s/^build_id=//p" /app/openpolaris-libgphoto2-provenance.txt 2>/dev/null' 2>/dev/null)"
if [ -z "$FWVER" ]; then
  detail NO_SSH "port 22 answered but /app/FwVer and the provenance file could not be read"
  exit 4
fi

BUILD_ID="$(printf '%s' "$FWVER" | sed -n '2p')"
FwV="$(printf '%s' "$FWVER" | sed -n '1p')"

if [ "$KEEPALIVE" = "1" ]; then
  # polestar_app's idle timer is short; without this the device can sleep
  # mid-session. Code 266 is the cheapest status ping.
  ( while :; do
      printf '1&266&0&#' | timeout 5 nc -w3 "$HOST" 9090 >/dev/null 2>&1 || true
      sleep 60
    done ) &
  KEEPALIVE_PID=$!
  trap '[ -n "${KEEPALIVE_PID:-}" ] && kill "$KEEPALIVE_PID" 2>/dev/null' EXIT INT TERM
  say "      keepalive started (pid $KEEPALIVE_PID)"
fi

detail READY "fwver=$FwV build_id=${BUILD_ID:-<none>} iface=$WIFI_IFACE"
exit 0
