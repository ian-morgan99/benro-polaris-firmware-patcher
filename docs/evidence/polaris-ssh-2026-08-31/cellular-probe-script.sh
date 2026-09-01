#!/bin/sh
# Polaris cellular hardware probe - safe read-only
# Saves results to /app/sd/HDR/probe-<timestamp>.txt
set +e
TS=$(date +%Y%m%d-%H%M%S)
OUT="/app/sd/HDR/probe-${TS}.txt"
{
  echo "===PROBE_SIM_INSERTED==="
  echo "TS: $(date)"
  echo
  echo "=== route ==="
  route -n 2>/dev/null || ip route
  echo
  echo "=== /dev/tty* ==="
  ls -l /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA* 2>&1
  echo
  echo "=== USB devices (VID:PID, idVendor+idProduct per /sys node) ==="
  for d in /sys/bus/usb/devices/*/; do
    v=$(cat "$d/idVendor" 2>/dev/null)
    p=$(cat "$d/idProduct" 2>/dev/null)
    cls=$(cat "$d/bDeviceClass" 2>/dev/null)
    ifname=$(cat "$d/net/ifname" 2>/dev/null)
    [ -n "$v" ] && echo "$(basename "$d")  $v:$p  cls=$cls  if=${ifname:-<none>}"
  done
  echo
  echo "=== USB driver binding check ==="
  for d in /sys/bus/usb/drivers/usbserial/*/; do
    [ -e "$d" ] || continue
    echo "usbserial bound: $(basename "$d")"
  done
  for d in /sys/bus/usb/drivers/option/*/; do
    [ -e "$d" ] || continue
    echo "option bound:    $(basename "$d")"
  done
  for d in /sys/bus/usb/drivers/cdc_acm/*/; do
    [ -e "$d" ] || continue
    echo "cdc_acm bound:   $(basename "$d")"
  done
  echo
  echo "=== pppd / chat / quectel userspace files present? ==="
  ls -l /usr/sbin/pppd /usr/sbin/chat /etc/ppp/peers/quectel-ppp* 2>&1
  echo
  echo "=== SIM socket (if there's a sysfs node for it) ==="
  ls /sys/class/*/sim* 2>/dev/null
  for d in /sys/class/*/; do
    n=$(basename "$d")
    case "$n" in *sim*|*SIM*|*wwan*|*modem*|*qc*) echo "class node: $n  ($(cat "$d/name" 2>/dev/null))" ;; esac
  done
  echo
  echo "=== dmesg tail (last 30 lines, look for usb/sim/cdc) ==="
  dmesg 2>/dev/null | tail -30
  echo
  echo "=== any /dev/cdc* / /dev/gsmmux* / /dev/wwan* ==="
  ls /dev/cdc* /dev/gsmmux* /dev/wwan* 2>&1
} > "$OUT" 2>&1
echo "wrote $OUT"
wc -l "$OUT"
