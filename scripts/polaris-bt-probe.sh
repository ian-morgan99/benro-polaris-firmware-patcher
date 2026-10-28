#!/usr/bin/env bash
# polaris-bt-probe.sh — shared Bluetooth reachability probe. SOURCE IT, don't run it.
#
# WHY THIS EXISTS (2026-10-27).
# Every wake path in this repo gated on `[ -e /dev/hci0 ] && command -v
# bluetoothctl` and, when that failed, degraded silently to "relying on AP/SSH
# already up". Two separate faults hid behind that one fallback, and both were
# then misattributed to the gimbal:
#
#   1. SANDBOX. VS Code here runs as a Flatpak. Inside it the Bluetooth adapter
#      may be absent, even though the host has it. On a normal Linux host the
#      controller is represented by /sys/class/bluetooth/hci0; /dev/hci0 is not
#      normally created.
#      bluetoothctl is not on PATH, AF_BLUETOOTH is seccomp-blocked
#      (Errno 97), and the proxied system bus exports only login1 — no
#      org.bluez. The host adapter is fine; the sandbox simply cannot see it.
#      The same portal trick this repo already uses for docker
#      (tests/test_plate_solving_present.py: docker_available() -> 'portal')
#      reaches it: `flatpak-spawn --host bluetoothctl ...`.
#
#   2. AN UNRELIABLE SCAN READING. On this host the adapter is a Qualcomm part
#      (usb 0489:e10a, Manufacturer: Qualcomm (29), LMP 5.3). The running
#      kernel has CONFIG_BT_HCIBTUSB_QCA unset and btqca is not loaded, so
#      btusb binds it by generic class match only and never runs the vendor
#      RAM-patch setup.
#
#      IMPORTANT CORRECTION (2026-10-27, same day): an earlier version of this
#      header asserted the adapter was deaf on the basis of "0 devices found"
#      and "acl:0". BOTH were measurement errors, not host faults:
#        * the greps looked for "New Device", but bluetoothctl prints
#          "[NEW] Device", and flatpak-spawn's PTY colourises it as
#          ESC[0;92mNEW ESC[0m -- so nothing could ever match;
#        * acl:0 is expected on an adapter that only scans, because LE
#          advertisements arrive as HCI events, not ACL packets.
#      With the output stripped and matched correctly the same adapter returns
#      real advertisements, i.e. it receives fine. The Qualcomm RAM-patch gap
#      above is real but has NOT been shown to break reception.
#      bluetoothctl still exits 0 after printing only "Attempting to connect",
#      which is exactly the false-success shape OpenPolaris #97 documents.
#
# A scan that returns nothing is therefore NOT evidence the gimbal is asleep.
# That inference sent several sessions chasing the device for reasons that were
# really measurement error or sandbox isolation (see docs/evidence/
# o-v17a-offline-validation-20261012/*, which record "host has no BT adapter" --
# it does have one, and it does receive; the reading was wrong).
#
# This module separates the four states and refuses to conflate them:
#
#   bt_resolve        where (if anywhere) bluetoothctl is reachable
#   bt_radio_liveness is the radio actually receiving anything?
#
# Verdicts from bt_radio_liveness (stable; safe to branch on):
#   0  RADIO_ALIVE       positively proven to receive (advertisement/inquiry hit)
#   1  LIVENESS_UNKNOWN  discovery ran but heard nothing -- proves nothing; a
#                        quiet room and a dead radio look identical here
#   2  NO_ADAPTER        no adapter or no bluetoothctl on any route
#   3  PROBE_BLOCKED     cannot probe from here (sandbox without a portal)
#
# Usage:
#   . "$(dirname "$0")/polaris-bt-probe.sh"
#   bt_resolve || exit 5
#   bt_radio_liveness 20 || { say "host radio is not receiving; see $(basename "$0")"; }
set -uo pipefail

# Do not clobber a caller's MAC: this file is sourced, and callers such as
# o-v17a-autonomous-install.sh set BT_MAC themselves (from their own env var).
: "${BT_MAC:=${POLARIS_BT:-48:E7:DA:D4:B5:72}}"

# Seam for tests: POLARIS_BT_DEV lets a test point the local-route check at any
# existing path so it can be exercised with stub binaries on PATH. The default
# is the Linux sysfs controller path; /dev/hci0 is not a normal host device
# node. Leave the override unset in production.
: "${POLARIS_BT_DEV:=/sys/class/bluetooth/hci0}"
BT_CMD=()                 # resolved invocation prefix, e.g. bluetoothctl | flatpak-spawn --host bluetoothctl
BT_ROUTE="none"           # local | portal | none
BT_PORTAL_CWD="${POLARIS_PORTAL_CWD:-$PWD}"

# flatpak-spawn inherits our cwd. If that is a sandbox-private directory (e.g.
# the sandbox's own /tmp) the spawn fails with "Failed to change to directory"
# even though the host binary is fine — so always run portal calls from a
# host-visible path.
bt_portal_cwd() {
  [ -d "$BT_PORTAL_CWD" ] || BT_PORTAL_CWD=/
  printf '%s' "$BT_PORTAL_CWD"
}

bt_in_flatpak() { [ -r /.flatpak-info ]; }

# bt_strip — remove ANSI/CSI sequences.
# flatpak-spawn allocates a PTY, so bluetoothctl colourises its output even when
# its stdout is a pipe: `[NEW]` arrives as ESC[0;92mNEW ESC[0m. A literal grep for
# "[NEW] Device" then matches nothing and a perfectly healthy radio is reported
# deaf. This cost a whole investigation on 2026-10-27; never scan without this.
bt_strip() { sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g'; }

# bt_exec <args...> — run bluetoothctl on whichever route bt_resolve picked.
# No timeout here: `timeout` execs a binary and cannot invoke a shell function,
# so callers that need a deadline must use bt_timeout instead.
bt_exec() {
  [ "${#BT_CMD[@]}" -gt 0 ] || return 127
  if [ "$BT_ROUTE" = "portal" ]; then
    ( cd "$(bt_portal_cwd)" && "${BT_CMD[@]}" "$@" )
  else
    "${BT_CMD[@]}" "$@"
  fi
}

# bt_timeout SECS <args...> — same, with a deadline applied to the real binary.
# The portal is run from a host-visible cwd (see bt_portal_cwd).
bt_timeout() {
  local t="$1"; shift
  [ "${#BT_CMD[@]}" -gt 0 ] || return 127
  if [ "$BT_ROUTE" = "portal" ]; then
    ( cd "$(bt_portal_cwd)" && timeout "$t" "${BT_CMD[@]}" "$@" )
  else
    timeout "$t" "${BT_CMD[@]}" "$@"
  fi
}

# bt_resolve — set BT_CMD/BT_ROUTE. Returns 0 when a route exists, 2 when not.
# It deliberately does NOT claim the radio works; only bt_radio_liveness does.
bt_resolve() {
  BT_CMD=(); BT_ROUTE="none"
  if command -v bluetoothctl >/dev/null 2>&1 && [ -e "$POLARIS_BT_DEV" ]; then
    BT_CMD=(bluetoothctl); BT_ROUTE="local"; return 0
  fi
  if command -v flatpak-spawn >/dev/null 2>&1; then
    # Probe, don't assume: the portal must actually answer.
    if ( cd "$(bt_portal_cwd)" && timeout 10 flatpak-spawn --host bluetoothctl list ) 2>/dev/null \
        | grep -qi 'Controller'; then
      BT_CMD=(flatpak-spawn --host bluetoothctl); BT_ROUTE="portal"; return 0
    fi
  fi
  # Last resort: the host binary may be visible under /run/host even when
  # flatpak-spawn is absent. It cannot open an mgmt socket from here, so this
  # is reported as blocked rather than usable.
  if [ -x "${POLARIS_BT_HOST_BIN:-/run/host/usr/bin/bluetoothctl}" ]; then
    BT_CMD=("${POLARIS_BT_HOST_BIN:-/run/host/usr/bin/bluetoothctl}"); BT_ROUTE="blocked"
  fi
  return 2
}

# bt_bin_timeout SECS <binary> <args...> — run an arbitrary host binary on the
# resolved route, with a deadline. Used for hcitool/hciconfig, which are not
# part of the bluetoothctl invocation.
bt_bin_timeout() {
  local t="$1" bin="$2"; shift 2
  if command -v "$bin" >/dev/null 2>&1; then
    timeout "$t" "$bin" "$@"
  elif [ "$BT_ROUTE" = "portal" ] && command -v flatpak-spawn >/dev/null 2>&1; then
    ( cd "$(bt_portal_cwd)" && timeout "$t" flatpak-spawn --host "$bin" "$@" )
  else
    return 127
  fi
}

# bt_acl_counter — print the hci0 ACL packet count, or empty if unreadable.
# CONTEXT ONLY. LE advertisements are delivered as HCI events, so an adapter
# that only ever scans legitimately shows acl:0; it is NOT a deafness signal.
# It is useful for spotting an adapter that has never carried any connection at
# all, which is a different question.
bt_acl_counter() {
  local out
  for d in /sys/class/bluetooth/hci0 /run/host/sys/class/bluetooth/hci0; do
    [ -d "$d" ] || continue
    # debugfs holds the real counters and is root-only; try it, then hciconfig.
    if [ -r "/sys/kernel/debug/bluetooth/$(basename "$d")/statistics/rx_acl" ]; then
      cat "/sys/kernel/debug/bluetooth/$(basename "$d")/statistics/rx_acl" 2>/dev/null; return 0
    fi
  done
  out="$(bt_bin_timeout 10 hciconfig hci0 2>/dev/null || true)"
  printf '%s' "$out" | sed -n 's/.*RX bytes:[0-9]* acl:\([0-9]*\).*/\1/p' | head -1
}

# bt_radio_liveness [SECS] — can we PROVE the host radio receives anything?
#
# Verdicts are deliberately asymmetric: "alive" requires positive evidence, an
# empty scan yields UNKNOWN rather than "deaf". Two reasons:
#   * bluetoothctl emits `[NEW] Device` only when a device is first added to
#     BlueZ's model, so a device already in the cache produces no line. Repeat
#     scans of the same room legitimately return zero even on a healthy radio.
#   * a genuinely quiet room has nothing to find. Classic inquiry in particular
#     returns nothing unless a peer is actively discoverable.
# RX byte growth during a scan is NOT usable as proof either: hciconfig's RX
# counter includes HCI command-complete events, which are responses to our own
# commands and arrive even with no RF traffic at all.
# So an empty scan means "cannot tell", never "deaf" and never "asleep".
bt_radio_liveness() {
  local secs="${1:-20}" out le classic acl
  # Always reset: a caller printing this after a successful probe must not see
  # counts left over from an earlier failed call in the same shell.
  BT_LIVENESS_DETAIL=""
  if [ "$BT_ROUTE" = "none" ]; then return 2; fi
  if [ "$BT_ROUTE" = "blocked" ]; then return 3; fi

  # LE scan. Confirm discovery actually started, otherwise the window proves nothing.
  # Output MUST be stripped of ANSI codes (see bt_strip) or every advertisement is
  # invisible and a working radio reads as deaf.
  out="$(bt_timeout "$((secs + 10))" --timeout "$secs" scan on 2>&1 | bt_strip || true)"
  if ! printf '%s' "$out" | grep -qi 'Discovering: yes'; then
    return 3
  fi
  # bluetoothctl prints `[NEW] Device <MAC> <name>`; the literal "New Device"
  # never matches.
  le="$(printf '%s\n' "$out" | grep -ciE '\[NEW\][[:space:]]+Device' || true)"

  if [ "${le:-0}" -gt 0 ]; then
    BT_LIVENESS_DETAIL="le=$le route=$BT_ROUTE"
    return 0
  fi

  # Classic inquiry as a second, independent transport. Note that `command -v`
  # is a shell builtin and cannot be invoked through the portal, so availability
  # is established by running hcitool and looking for its banner -- which also
  # proves it can open an HCI socket, not merely that the binary exists.
  classic=""
  local cinq
  if command -v hcitool >/dev/null 2>&1; then
    cinq="$(timeout 30 hcitool scan --flush 2>/dev/null || true)"
  elif [ "$BT_ROUTE" = "portal" ]; then
    cinq="$(bt_bin_timeout 30 hcitool scan --flush 2>/dev/null || true)"
  else
    cinq=""
  fi
  if printf '%s' "$cinq" | grep -qi 'Scanning'; then
    classic="$(printf '%s\n' "$cinq" | grep -cE '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}' || true)"
  fi

  if [ "${classic:-0}" -gt 0 ]; then
    BT_LIVENESS_DETAIL="le=${le:-0} classic=$classic route=$BT_ROUTE"
    return 0
  fi

  # Both transports silent. This proves nothing about the radio -- see the
  # function header. acl_rx is recorded for context only.
  acl="$(bt_acl_counter 2>/dev/null || true)"
  BT_LIVENESS_DETAIL="le=0 classic=${classic:-n/a} acl_rx=${acl:-unreadable} route=$BT_ROUTE"
  return 1
}

# bt_wake_pulse — send one wake pulse and report only what is verifiable.
# Returns 0 ONLY if the GATT link is established and still held afterwards.
# Never treat a zero exit from bluetoothctl as success: it prints
# "Attempting to connect ..." and exits 0 before BlueZ has resolved anything,
# and the link then aborts locally (OpenPolaris #97).
bt_wake_pulse() {
  local mac="${1:-$BT_MAC}"
  [ "${#BT_CMD[@]}" -gt 0 ] || return 2
  bt_timeout 25 --timeout 15 connect "$mac" >/dev/null 2>&1
  sleep 2
  bt_timeout 10 info "$mac" 2>/dev/null | grep -q 'Connected: yes'
}
