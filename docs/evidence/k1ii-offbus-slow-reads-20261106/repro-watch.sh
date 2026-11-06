#!/bin/sh
# Capture driver-level evidence during a live reproduction of the K-1 II
# symptoms. Run this BEFORE reproducing, then reproduce, then read the log.
#
# Records, every 2s:
#   - whether the camera is enumerated and its bus/speed (hub vs direct)
#   - pgphoto pid + thread states (detects a stall at the moment it happens)
#   - every line the driver writes to Clog.txt, which now names the refusal
#     reason: capability (GP_ERROR_NOT_SUPPORTED / "not supported") versus
#     readiness (_pentax_readiness_preflight busy/idle/transport)
#   - wall-clock timing of /api/snapshot so slow reads are measurable
LOG=/tmp/k1ii-repro.log
CLOG=/app/Clog.txt
: > "$LOG"
csize=$(wc -c < "$CLOG" 2>/dev/null || echo 0)
echo "=== repro watch started $(date) ===" >> "$LOG"
i=0
while [ $i -lt 900 ]; do
  i=$((i+1))
  usb=$(grep -lq 25fb /sys/bus/usb/devices/*/idVendor 2>/dev/null && echo present || echo absent)
  spd=$(for d in /sys/bus/usb/devices/*/idVendor; do
          [ "$(cat $d 2>/dev/null)" = "25fb" ] && { p=${d%/idVendor}; \
            grep -h speed "$p"/speed 2>/dev/null | sed 's/^/speed=/'; }
        done | head -1)
  pid=$(pidof pgphoto.stage2ondisk | awk '{print $1}')
  st=""
  [ -n "$pid" ] && for t in /proc/$pid/task/*; do
        s=$(awk '{print $3}' $t/stat 2>/dev/null)
        w=$(cat $t/wchan 2>/dev/null)
        st="$st $s:$w"
      done
  nsize=$(wc -c < "$CLOG" 2>/dev/null || echo 0)
  if [ "$nsize" != "$csize" ]; then
    echo "--- t+$((i*2))s NEW Clog bytes ($csize -> $nsize) ---" >> "$LOG"
    tail -c +$((csize+1)) "$CLOG" 2>/dev/null | cut -c1-200 >> "$LOG"
    csize=$nsize
  fi
  echo "t+$((i*2))s usb=$usb ${spd:-speed=?} pgphoto=${pid:-none} threads:$st" >> "$LOG"
  sleep 2
done
echo "=== repro watch ended ===" >> "$LOG"
