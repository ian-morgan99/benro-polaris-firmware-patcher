#!/bin/sh
# ============================================================================
#  Benro Polaris cellular modem loader (Phase 3, optional)
#
#  Stock Polaris firmware (FwVer 4.0.0.32) ships the full Quectel PPP userspace
#  (pppd, chat, /etc/ppp/peers/quectel-ppp, polestar_app glue) but omits the
#  kernel-side USB-serial host driver stack (usbserial/option/cdc_acm/qcserial).
#  When --cellular-modules is supplied, this loader inserts those four modules
#  in the correct order so a Quectel EC25 / EG25 / Sierra AirCard can be used
#  to bring up a cellular data link.
#
#  Placed at /app/komod/cellular_load.sh by the patcher; called from bootapp
#  after sp_load3559v200 returns.  This is a no-op when the cellular modules
#  are not present in /app/komod/, or when no supported modem is plugged in.
#
#  Load order matters:  usbserial is the parent of option/cdc_acm/qcserial, so
#  it must land first.  qcserial must claim VID 2c7c BEFORE the generic option
#  driver gets a chance, otherwise the modem registers as a plain "option"
#  device and the Quectel-specific power-management / QMI quirks are lost.
#
#  Unload order is the strict reverse.
# ============================================================================
set +e                                       # insmod/rmmod failures are non-fatal

cd /app/komod/

# --- quick VID-gate: only proceed if a known modem is present ---------------
# /sys/bus/usb/devices/*/idVendor is the most reliable place to ask; the
# Quectel vendor ID is 0x2c7c, Sierra Wireless is 0x1199.  If neither is
# there, the modules are useless; skip the insmods to keep the kernel log
# clean and to avoid breaking ttyUSB* for any future wired serial port.
HAS_MODEM=0
for vid in /sys/bus/usb/devices/*/idVendor; do
  [ -r "$vid" ] || continue
  v=$(cat "$vid" 2>/dev/null)
  case "$v" in
    2c7c|1199) HAS_MODEM=1; break;;
  esac
done

if [ "$HAS_MODEM" -eq 0 ]; then
  # No supported modem.  Stay quiet: this is the expected state on units
  # without the SIM-socket variant, or before a modem enumerates.
  exit 0
fi

# --- order: foundation, then generic clients, then the Quectel-specific grab -
for mod in usbserial.ko option.ko cdc_acm.ko qcserial.ko; do
  if [ -f "$mod" ]; then
    insmod "$mod"
  fi
done

# Surface a one-liner so /app/Mlog.txt shows what happened.  If the loader is
# being run by hand (e.g. from the on-device shell) the same echo helps.
echo "[cellular] modules loaded (usbserial/option/cdc_acm/qcserial)"
exit 0
