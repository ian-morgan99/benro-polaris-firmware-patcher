#!/bin/bash
# .68 stability run per #180: three consecutive captures, each recorded
# separately (first-shot behaviour is diagnostic), with device health sampled
# before and after so a leak or a restart is visible rather than assumed.
set -u
cd /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher
OUT=docs/evidence/o-v17c-stability-20261019
mkdir -p "$OUT"
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
D=root@192.168.0.1

health () { # $1 = label
  echo "### HEALTH $1 $(date -u +%H:%M:%SZ)"
  $SSH $D 'echo "uptime=$(cut -d. -f1 /proc/uptime)"; echo "memfree_kb=$(grep MemFree /proc/meminfo | awk "{print \$2}")";
    for p in 249 $(cat /var/run/openpolaris-pgphoto.pid 2>/dev/null); do
      [ -d /proc/$p ] || { echo "pid=$p GONE"; continue; }
      echo "pid=$p comm=$(cat /proc/$p/comm) rss_kb=$(awk "/VmRSS/{print \$2}" /proc/$p/status) fds=$(ls /proc/$p/fd | wc -l) threads=$(awk "/Threads/{print \$2}" /proc/$p/status)";
    done
    echo "dmesg_faults=$(dmesg | grep -ciE "segfault|oom-kill|out of memory|kernel panic")"
    echo "camera=$(grep -l 25fb /sys/bus/usb/devices/*/idVendor 2>/dev/null | wc -l)"' 2>/dev/null
  echo
}

health BEFORE | tee "$OUT/health.txt"
: > "$OUT/shots.txt"
pass=0
for n in 1 2 3; do
  echo "=== SHOT $n start $(date -u +%H:%M:%SZ) ===" | tee -a "$OUT/shots.txt"
  timeout 300 python3 scripts/canary-probe.py --shot --expected-files 1 \
      --expected-sw 6.0.0.54.68 >> "$OUT/shots.txt" 2>&1
  rc=$?
  echo "=== SHOT $n rc=$rc end $(date -u +%H:%M:%SZ) ===" | tee -a "$OUT/shots.txt"
  [ $rc -eq 0 ] && pass=$((pass+1))
  sleep 5
done
health AFTER | tee -a "$OUT/health.txt"
echo "RESULT: $pass/3 shots passed" | tee -a "$OUT/shots.txt"
