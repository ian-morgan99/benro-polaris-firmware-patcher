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
# A missing BLE advertisement is NOT evidence of a sleeping device. The rig's LE
# advertising registration fails on every boot (Mlog: "Failed to register
# advertising object"), and bluetoothctl prints `[NEW] Device` only once per
# cached device, so an empty scan proves nothing in either direction. ASLEEP is
# therefore decided by AP absence via the Wi-Fi scan, which does not depend on
# the Bluetooth stack at all. The host-radio probe in polaris-bt-probe.sh runs
# for information only and never changes the verdict.
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
#   --no-radio-check    skip the informational host-radio probe (does not
#                       change any verdict)
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
RADIO_CHECK=1

while [ $# -gt 0 ]; do
  case "$1" in
    --wake) WAKE=1; shift;;
    --keepalive) KEEPALIVE=1; shift;;
    --wait) WAIT_AP_SECS="$2"; shift 2;;
    --scan) SCAN_SECS="$2"; shift 2;;
    --no-radio-check) RADIO_CHECK=0; shift;;
    --quiet) QUIET=1; shift;;
    -h|--help) sed -n '2,49p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

say() { [ "$QUIET" = "1" ] || printf '%s\n' "$*"; }

VERDICT="UNKNOWN"
detail() { VERDICT="$1"; shift; printf 'VERDICT=%s' "$VERDICT"; printf ' %s' "$@"; printf '\n'; }

# ---------------------------------------------------------------------------
# Host-tool routing. VS Code here runs as a Flatpak: nmcli/ip/ssh/bluetoothctl
# are absent from PATH and /dev/hci0 does not exist, even though the host has
# all of them. The portal reaches them, exactly as this repo already does for
# docker (see tests/test_plate_solving_present.py, docker_available()). Without
# this the script exits HOST_TOOLING from inside the editor and every caller
# concludes "no adapter".
# ---------------------------------------------------------------------------
HOST_PREFIX=()
if command -v nmcli >/dev/null 2>&1 && command -v ip >/dev/null 2>&1 \
   && command -v ssh >/dev/null 2>&1; then
  :   # plain host shell, no routing needed
elif command -v flatpak-spawn >/dev/null 2>&1 \
     && ( cd "$PWD" && timeout 10 flatpak-spawn --host nmcli --version ) >/dev/null 2>&1; then
  HOST_PREFIX=(flatpak-spawn --host)
else
  for tool in nmcli ip ssh; do
    command -v "$tool" >/dev/null 2>&1 || { detail HOST_TOOLING "missing=$tool (no portal route either; sandbox=$( [ -r /.flatpak-info ] && echo yes || echo no ))"; exit 5; }
  done
fi
# run_host [OPTIONS] <cmd> [args...] — run a host command on the resolved route.
#   run_host --timeout SECS cmd...   apply the deadline to the real binary
#
# The deadline MUST be applied to the real binary, not to this function:
# `timeout N run_host nmcli ...` fails because timeout execs a binary and cannot
# invoke a shell function. That silently returned empty output here, so
# ap_visible() always reported "not broadcasting" and an awake rig was recorded
# as ASLEEP. Verified live on 2026-10-27.
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

# Shared Bluetooth reachability probe: distinguishes "no adapter visible from
# here" from "adapter present but deaf". Never infer a sleeping device from an
# empty scan without it. If the module is missing we must still not fall back to
# claiming ASLEEP, so the stub below forces the radio check to fail closed.
BT_PROBE_LIB="$(cd "$(dirname "$0")" && pwd)/polaris-bt-probe.sh"
if [ -r "$BT_PROBE_LIB" ]; then
  # shellcheck source=./polaris-bt-probe.sh
  . "$BT_PROBE_LIB"
else
  BT_ROUTE="none"; BT_CMD=()
  bt_resolve() { return 2; }
  bt_exec() { return 127; }
  bt_timeout() { return 127; }
  bt_bin_timeout() { return 127; }
  bt_acl_counter() { :; }
  bt_radio_liveness() { BT_LIVENESS_DETAIL="probe module missing: $BT_PROBE_LIB"; return 3; }
fi
bt_resolve || true
HAVE_BT=0
if [ "$BT_ROUTE" = "local" ] || [ "$BT_ROUTE" = "portal" ]; then HAVE_BT=1; fi

# ap_visible — is the gimbal's AP broadcasting?
#
# nmcli's terse (-t) output ESCAPES colons inside field values, so the BSSID
# prints as `48\:E7\:DA\:D4\:B5\:73`. Grepping for "48:E7:DA" therefore never
# matched and the AP was always reported absent -- which made this script return
# ASLEEP/BOOTING against a rig that was demonstrably awake and associated.
# Verified live on 2026-10-27:
#     $ nmcli -t -f BSSID,SSID dev wifi list | grep polaris | cat -A
#     48\:E7\:DA\:D4\:B5\:73:polaris_d13e86$
# Strip the backslashes before matching. Match on OUI or SSID so a future
# firmware SSID change does not silently break detection.
ap_visible() {
  run_host --timeout 15 nmcli -t -f BSSID,SSID dev wifi list --rescan yes 2>/dev/null \
    | tr -d '\\' \
    | grep -iE "$AP_OUI|$AP_SSID" | head -1
}

associated() {
  run_host nmcli -t -f NAME,DEVICE,STATE connection show --active 2>/dev/null \
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
  bt_timeout "$((SCAN_SECS + 5))" --timeout "$SCAN_SECS" scan on >"$out" 2>&1
  # bluetoothctl prints `[NEW] Device <MAC> <name>`; matching the literal
  # "New Device <MAC>" never matches and made every scan look empty.
  grep -qiE "\[NEW\][[:space:]]+Device[[:space:]]+$BT_MAC" "$out" && found=0
  rm -f "$out"
  return "$found"
}

say "--- polaris preflight $(date -u +%FT%TZ) ---"
say "      host tools: route=${HOST_PREFIX[0]:-local}  bluetooth=$BT_ROUTE"

# 1. Live BLE advertisement. Absent with no AP, this is a sleeping or powered
#    off device, which is a different problem from a broken firmware image --
#    but only if the host radio can receive at all, so an empty scan is never
#    sufficient on its own (see polaris-bt-probe.sh).
BLE=unknown
if [ "$HAVE_BT" = "1" ]; then
  say "[1/5] BLE advertisement (cache cleared, ${SCAN_SECS}s window)..."
  if ble_advertising; then BLE=yes; say "      live advertisement seen from $BT_MAC"
  else BLE=no; say "      no advertisement (cached entries ignored)"; fi
else
  say "[1/5] BLE skipped (bluetoothctl unreachable: route=$BT_ROUTE)"
fi

AP="$(ap_visible)"
say "[2/5] AP broadcast..."
if [ -n "$AP" ]; then
  say "      visible: $AP"
else
  say "      not broadcasting"
  if [ "$WAKE" = "1" ]; then
    [ "$HAVE_BT" = "1" ] || { detail HOST_TOOLING "bluetoothctl unreachable for --wake (route=$BT_ROUTE)"; exit 5; }
    say "      sending BLE wake pulse, waiting up to ${WAIT_AP_SECS}s"
    # Report the link result honestly: bluetoothctl prints "Attempting to
    # connect ..." and exits 0 before BlueZ has resolved anything, so the
    # connect call is not evidence. Only a held link counts.
    if bt_wake_pulse "$BT_MAC"; then
      say "      wake pulse: GATT link established and held"
    else
      say "      wake pulse: no held link (bluetoothctl may still exit 0; see OpenPolaris #97)"
    fi
    deadline=$(( $(date +%s) + WAIT_AP_SECS ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
      sleep 8
      AP="$(ap_visible)"
      [ -n "$AP" ] && { say "      visible after wait: $AP"; break; }
    done
  fi
fi

if [ -z "$AP" ]; then
  # The AP check is the reliable one: nmcli's Wi-Fi scan works regardless of the
  # Bluetooth stack, and the SoC, its AP and its BLE radio sleep together, so no
  # AP means no device. Do NOT gate on the BLE scan:
  #   * the rig's LE advertising registration fails on every boot (Mlog logs
  #     "Failed to register advertising object" then retries), so a live rig may
  #     simply never advertise LE;
  #   * bluetoothctl prints `[NEW] Device` only when a device is first added to
  #     BlueZ's model, so cached devices produce no line on repeat scans.
  # An empty BLE scan therefore proves nothing in either direction. The radio
  # probe below is informational context only and never changes the verdict.
  if [ "$RADIO_CHECK" = "1" ] && [ "$HAVE_BT" = "1" ]; then
    say "      (informational) checking host radio can receive..."
    rc=0; bt_radio_liveness "$SCAN_SECS" || rc=$?
    case "$rc" in
      0) say "      radio receives: ${BT_LIVENESS_DETAIL:-}"
         say "      NOTE: the rig may still not advertise LE even when awake (see Mlog 'Failed to register advertising object')";;
      1) say "      radio heard nothing (${BT_LIVENESS_DETAIL:-}) -- inconclusive, not evidence of a dead radio or a sleeping rig";;
      2) say "      no Bluetooth adapter reachable from here (route=$BT_ROUTE); BLE wake unavailable, Wi-Fi checks unaffected";;
      *) say "      cannot probe host radio (${BT_LIVENESS_DETAIL:-}); BLE wake unavailable, Wi-Fi checks unaffected";;
    esac
  fi
  if [ "$BLE" = "yes" ]; then
    detail BOOTING "BLE advertisement present but AP not broadcasting; the device is waking or hostapd is not up. Wait, or power-cycle."
    exit 3
  fi
  detail ASLEEP "no AP broadcast; the SoC is asleep or unpowered. Power-cycle it, or check the battery. (BLE absence was not used: the rig does not reliably advertise LE.)"
  exit 1
fi

# 3. Association must be to the gimbal, on the Wi-Fi interface.
say "[3/5] association..."
ASSOC="$(associated)"
if [ -z "$ASSOC" ]; then
  say "      not associated; attempting join"
  if ! run_host --timeout 30 nmcli device wifi connect "$AP_SSID" >/dev/null 2>&1; then
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
ROUTE="$(run_host --timeout 10 ip route get "$HOST" 2>/dev/null | head -1)"
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

FWVER="$(run_host --timeout 20 ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
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
