#!/usr/bin/env bash
# fix-bt-adapter-qca.sh — install the missing QCA2066 firmware subdirectory for
# the workstation's built-in Bluetooth adapter (usb 0489:e10a, WCN6855 family).
#
# WHY THIS EXISTS
# The adapter is a Qualcomm WCN6855-family part. btusb matches it with the
# BTUSB_QCA_WCN6855 quirk (confirmed: the compiled table in
# /lib/modules/$(uname -r)/kernel/drivers/bluetooth/btusb.ko contains
# 0489:e10a alongside e0c7/e0c9/e103/e10d), and QCA vendor setup is compiled
# into btusb on this kernel (btusb_setup_qca_load_rampatch / _load_nvm are
# present as local symbols, so the legacy btqca module is not used and loading
# it would do nothing).
#
# Vendor setup resolves firmware through qca_get_fw_subdirectory(): for rom
# version 0x00130201 with board id 0x030A or 0x030B it looks in a SoC-specific
# subdirectory:
#
#     qca/QCA2066/rampatch_usb_00130201.bin
#     qca/QCA2066/nvm_usb_00130201_030a.bin
#
# Upstream linux-firmware ships both. This machine has neither, and has no
# qca/QCA2066 directory at all — the installed linux-firmware predates it:
#
#     $ ls /lib/firmware/qca/QCA2066/
#     No such file or directory
#
# The flat fallback (qca/rampatch_usb_00130201.bin) IS present, so this only
# bites when the controller reports one of those two board ids.
#
# HONEST SCOPE — READ BEFORE EXPECTING A FIX
# This repo already investigated this adapter and CORRECTED an over-confident
# conclusion. scripts/polaris-bt-probe.sh states plainly that the Qualcomm
# RAM-patch gap is real but "has NOT been shown to break reception", and that
# two earlier indicators were measurement errors, not host faults:
#   * grepping for "New Device" instead of bluetoothctl's actual "[NEW] Device";
#   * treating acl:0 as deafness, when LE advertisements arrive as HCI events,
#     not ACL packets.
# Separately, docs/evidence/rig-le-advertising-absent-20261027/SUMMARY.md found
# the rig itself fails to register LE advertising on every boot
# ("Failed to register advertising object", reg_fail=1), so a Linux BLE client
# finds nothing regardless of how good this host's radio is.
#
# A THIRD, MORE LIKELY ROOT CAUSE FOUND 2026-11-27 — THE QUIRK MAY NEVER APPLY
# The repo attributes the gap to "CONFIG_BT_HCIBTUSB_QCA unset and btqca not
# loaded". On this kernel that is obsolete: QCA setup is compiled INTO btusb
# (btusb_setup_qca_load_rampatch / _load_nvm are local symbols of btusb.ko), so
# btqca is irrelevant and loading it would do nothing.
#
# The real question is whether btusb_setup_qca runs at all, and the evidence
# says it does not:
#
#   $ journalctl -k -b | grep -ci rampatch      # 0
#   $ journalctl -k -b | grep -ci Qualcomm      # 0
#   $ journalctl -k -b | grep -c "Bluetooth:"   # 13  (log is complete)
#
# btusb logs "using rampatch file: ..." on success and "failed to request
# rampatch file: ..." on failure. Neither appears across 8605 boot lines, so no
# firmware request was ever made — the missing files are not the binding fault.
#
# Why: usb_match_id() returns the FIRST matching entry, and entry #1 of
# btusb_table is { USB_DEVICE_INFO(0xe0, 0x01, 0x01) } with driver_info = 0.
# This device reports bDeviceClass/SubClass/Protocol = e0/01/01 (verified from
# /sys/bus/usb/devices/1-11), so the generic entry matches first and the
# BTUSB_QCA_WCN6855 flag on the 0489:e10a row is never consulted. Without that
# flag, data->setup_on_usb = btusb_setup_qca is never assigned.
#
# Consequence: installing qca/QCA2066/* alone is very likely a NO-OP. It is
# still correct hygiene — the tree is incomplete relative to upstream — but do
# not expect it to change behaviour. The verification below therefore checks for
# evidence that vendor setup RAN, and says so explicitly if it did not.
#
# If BLE wake genuinely must work from this host, the options are a kernel with
# the quirk actually applied to this device (or an out-of-tree match override),
# or a USB Bluetooth dongle. Neither is achievable by dropping in firmware.
#
# Usage:  sudo ./fix-bt-adapter-qca.sh            # install + reload + verify
#         sudo ./fix-bt-adapter-qca.sh --dry-run  # show what would change
#         sudo ./fix-bt-adapter-qca.sh --revert   # restore backups
set -euo pipefail

FW_DIR="/lib/firmware/qca/QCA2066"
SRC_DIR="${SRC_DIR:-/tmp/qca-fix}"
FILES=(rampatch_usb_00130201.bin nvm_usb_00130201_030a.bin)

# sha256 of the blobs as fetched from linux-firmware main on 2026-11-27.
# Pinned deliberately: a wrong or truncated blob bricks the radio until reboot,
# and btusb reports it only as "rampatch file version did not match with firmware".
declare -A WANT_SHA=(
  [rampatch_usb_00130201.bin]="84a31a4c8b4bbbc6c2b7cf7b1de4153c8e6e00a221df8fbecaa9640931bdc4a7"
  [nvm_usb_00130201_030a.bin]="819733b463b264a44eaa1b07c75a96ecacdf020cc432daba1b2d4a3ce483a955"
)

MODE="install"
case "${1:-}" in
  --dry-run) MODE="dry-run" ;;
  --revert)  MODE="revert"  ;;
  "")        ;;
  *) echo "unknown option: $1 (use --dry-run or --revert)" >&2; exit 2 ;;
esac

log() { printf '[bt-fix] %s\n' "$*"; }
die() { printf '[bt-fix] ERROR: %s\n' "$*" >&2; exit 1; }

# --dry-run only reads, so it is useful unprivileged; install/revert need root.
if [ "$MODE" != "dry-run" ] && [ "$(id -u)" -ne 0 ]; then
  die "must run as root to ${MODE} (installs into /lib/firmware and rebinds btusb); --dry-run needs no privileges"
fi

# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------
if [ "$MODE" = "revert" ]; then
  if [ ! -d "$FW_DIR" ]; then
    log "nothing to revert: $FW_DIR does not exist"
    exit 0
  fi
  for f in "${FILES[@]}"; do
    if [ -e "$FW_DIR/$f.btfix-bak" ]; then
      mv -f "$FW_DIR/$f.btfix-bak" "$FW_DIR/$f"
      log "restored $FW_DIR/$f"
    else
      rm -f "$FW_DIR/$f"
      log "removed $FW_DIR/$f (no prior copy to restore)"
    fi
  done
  rmdir "$FW_DIR" 2>/dev/null || true
  log "reverted. Rebind btusb to take effect:"
  log "  modprobe -r btusb && sleep 2 && modprobe btusb   (or reboot)"
  exit 0
fi

# ---------------------------------------------------------------------------
# Preflight: validate sources before touching anything
# ---------------------------------------------------------------------------
log "adapter: $(cat /sys/class/bluetooth/hci0/address 2>/dev/null || echo 'no hci0')"
log "chip:    $(for d in /sys/bus/usb/devices/*/; do
        [ -e "$d/idVendor" ] || continue
        v=$(cat "$d/idVendor"); p=$(cat "$d/idProduct")
        if [ "$v" = "0489" ] && [ "$p" = "e10a" ]; then
                printf '%s:%s (%s)\n' "$v" "$p" "$(basename "$d")"; break
        fi
done)"

for f in "${FILES[@]}"; do
  src="$SRC_DIR/$f"
  [ -f "$src" ] || die "missing source $src (fetch it first; see header)"
  got=$(sha256sum "$src" | cut -d' ' -f1)
  want="${WANT_SHA[$f]}"
  if [ "$got" != "$want" ]; then
    # A cgit error page is the common failure here: it is HTML, ~3 KB, and
    # silently "installs" as a blob that the controller rejects.
    head -c 15 "$src" | grep -qi '<!doctype\|<html' && die "$src is an HTML page, not firmware"
    die "$src hash mismatch
       expected $want
       got      $got"
  fi
  log "verified $f ($(stat -c %s "$src") bytes)"
done

if [ "$MODE" = "dry-run" ]; then
  log "dry run: would create $FW_DIR and install:"
  for f in "${FILES[@]}"; do log "  $FW_DIR/$f"; done
  log "existing files would be kept as <name>.btfix-bak"
  exit 0
fi

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
mkdir -p "$FW_DIR"
for f in "${FILES[@]}"; do
  if [ -e "$FW_DIR/$f" ]; then
    [ -e "$FW_DIR/$f.btfix-bak" ] || cp -a "$FW_DIR/$f" "$FW_DIR/$f.btfix-bak"
    log "kept existing $f as $f.btfix-bak"
  fi
  install -m 0644 "$SRC_DIR/$f" "$FW_DIR/$f"
  log "installed $FW_DIR/$f"
done

# Rebind btusb so probe re-runs vendor setup. Power-cycling via bluetoothctl is
# NOT enough: the QCA patch is applied at USB probe, not at hci open.
log "rebinding btusb (this briefly drops the adapter)"
if modprobe -r btusb 2>/dev/null; then
  sleep 2
  modprobe btusb || die "btusb reload failed — reboot to recover"
else
  log "could not unload btusb (in use); a reboot is required instead"
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
sleep 4
log "kernel lines for hci0 since rebind:"
journalctl -k --no-pager --since "-1 min" 2>/dev/null \
  | grep -iE "hci0|rampatch|nvm|qca|wcn|Qualcomm" | sed 's/^/    /' || log "    (none)"

# Three distinct outcomes, quoted from btusb. Distinguishing them matters: the
# third one means the firmware was never even requested, so installing it fixed
# nothing and chasing the blobs further is wasted effort.
#   "using rampatch file: ..."                      -> vendor setup RAN (success)
#   "failed to request rampatch file: ... (-2)"     -> ran, but a blob is wrong/missing
#   "rampatch file version did not match with firmware" -> ran, blob is for another rom
#   (nothing at all)                                -> setup never ran; quirk not applied
KLOG=$(journalctl -k --no-pager --since "-1 min" 2>/dev/null || true)
if printf '%s\n' "$KLOG" | grep -qiE "using rampatch file|QCA: patch rome"; then
  log "vendor setup RAN and accepted the firmware — this is the success signal."
elif printf '%s\n' "$KLOG" | grep -qiE "failed to request rampatch|version did not match|don't support firmware"; then
  log "vendor setup RAN but rejected the firmware — see the lines above."
  log "Do not conclude the radio is broken; confirm the board id the controller reports."
elif printf '%s\n' "$KLOG" | grep -qiE "rampatch|qca|Qualcomm|wcn"; then
  log "some QCA activity logged, but no rampatch acceptance — inspect the lines above."
else
  log "NOTHING LOGGED: btusb never requested any QCA firmware, so the quirk is not"
  log "being applied to this device at all (see header). Installing these blobs"
  log "cannot change behaviour. Do not report this as a fixed adapter."
fi

# Scan check with the pattern bluetoothctl actually prints, ANSI stripped.
# Grepping "New Device" can never match and previously produced false "deaf
# radio" conclusions (see scripts/polaris-bt-probe.sh header).
log "30 s LE scan (correct [NEW] Device pattern, ANSI stripped):"
if command -v bluetoothctl >/dev/null 2>&1; then
  OUT=$(timeout 40 bluetoothctl --timeout 30 scan on 2>&1 \
        | sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g' || true)
  N=$(printf '%s\n' "$OUT" | grep -c "\[NEW\] Device" || true)
  log "  advertisements received: $N"
  printf '%s\n' "$OUT" | grep "\[NEW\] Device" | head -5 | sed 's/^/    /'
  if [ "${N:-0}" -eq 0 ]; then
    log "  zero. This is NOT proof the adapter is deaf and NOT proof the rig is"
    log "  asleep. The rig fails to register LE advertising on every boot"
    log "  (docs/evidence/rig-le-advertising-absent-20261027), so expect this."
  fi
else
  log "  bluetoothctl unavailable here — run the scan on the host:"
  log "  bluetoothctl --timeout 30 scan on | sed -r 's/\\x1b\\[[0-9;]*[a-zA-Z]//g' | grep -c '\\[NEW\\] Device'"
fi

log "done."
