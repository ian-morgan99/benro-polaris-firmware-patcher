#!/bin/sh
# Capture driver-level evidence for the K-1 II symptoms.
#
# Phase 1: wait quietly for the camera to re-enumerate (logs only transitions, so
#   it can sit for hours without filling /tmp).
# Phase 2: once present, sample every 2 s for 30 minutes and record:
#   - link speed, so a hub vs direct attachment is visible at the moment of failure
#   - pgphoto pid + every thread's state/wait channel (a stall shows as D state or
#     a USB wait queue -- what after-the-fact sampling could not see)
#   - new bytes appended to /app/Clog.txt, which now names WHY the driver refused:
#     capability (GP_ERROR_NOT_SUPPORTED, returned before touching the wire) versus
#     readiness (_pentax_readiness_preflight busy/idle/transport).
LOG=/tmp/k1ii-repro.log
CLOG=/app/Clog.txt
: > "$LOG"
present() { grep -lq 25fb /sys/bus/usb/devices/*/idVendor 2>/dev/null; }

echo "=== armed $(date) : waiting for the K-1 II to re-enumerate ===" >> "$LOG"
i=0
while ! present; do
  i=$((i+1))
  [ $i -ge 3600 ] && { echo "=== gave up after 3 h of waiting ===" >> "$LOG"; exit 0; }
  sleep 3
done
echo "=== camera present $(date) : sampling every 2 s for 30 min ===" >> "$LOG"

csize=$(wc -c < "$CLOG" 2>/dev/null || echo 0)
i=0
while [ $i -lt 900 ]; do
  i=$((i+1))
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
  echo "t+$((i*2))s usb=present ${spd:-speed=?} pgphoto=${pid:-none} threads:$st" >> "$LOG"
  sleep 2
done
echo "=== sampling ended $(date) ===" >> "$LOG"
