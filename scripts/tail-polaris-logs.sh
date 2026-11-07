#!/usr/bin/env bash
# tail-polaris-logs.sh — continuously mirror Mlog/Clog + crash log off a Benro
# Polaris gimbal so a fault is not lost to SD rotation.
#
# WHY THIS EXISTS. /app/Mlog.txt and /app/Clog.txt are truncated whenever the
# stock checkGphotoTask watchdog restarts pgphoto, and the SD copies in
# /app/sd/system/log rotate on size. During the 2026-11-03 K-3 III investigation
# a pgphoto SIGSEGV was followed by a watchdog restart that truncated Clog.txt
# to 0 bytes within seconds — the death scene was only recoverable because it
# had already been copied off. A crash is therefore routinely invisible unless
# something is watching continuously.
#
# WHY PER-FILE dd AND NOT tar. scripts/pull-mlog-clog.sh tars the whole log
# directory; on this card that aborts part-way with "tar: read error:
# Input/output error" (the FAT chain has a bad cluster, dmesg shows repeated
# fat_bmap_cluster: request beyond EOF). Each file is therefore fetched
# individually with dd, which tolerates the bad region.
#
# Usage:
#   ./scripts/tail-polaris-logs.sh [user@host] [output-dir] [interval-secs]
#   ./scripts/tail-polaris-logs.sh root@192.168.0.1 /tmp/polaris-tail 15
#
# Output: <output-dir>/<timestamp>/ with a numbered snapshot per poll:
#   snap-0001/{Mlog.txt,Clog.txt,stage2-crash.log,state.txt}
# A new snapshot is written only when at least one source changed size, so an
# idle device costs almost nothing. Ctrl-C to stop; the last snapshot is kept.
set -uo pipefail

HOST="${1:-root@192.168.0.1}"
OUTROOT="${2:-/tmp/polaris-tail}"
INTERVAL="${3:-15}"
TS="$(date -u +%Y%m%d-%H%M%S)"
OUT="$OUTROOT/$TS"

mkdir -p "$OUT" || exit 1

echo "==> identity check (must be the gimbal, not the router)..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  'cat /app/FwVer; ls /app/lib/stage2/pgphoto.stage2ondisk /app/bin/polestar_app' || {
    echo "FAILED: $HOST is not answering like a patched Polaris gimbal." >&2
    echo "  - Joined to the polaris_* AP (BSSID 48:E7:DA...) rather than home Wi-Fi?" >&2
    echo "  - Note: /app/lib/stage2/ exists only on a Stage-2 (patched) build." >&2
    exit 1
  }

# Sources mirrored every poll. Kept as one list so state.txt and the copies agree.
FILES="/app/Mlog.txt /app/Clog.txt /app/stage2-crash.log"

snap=0
prev=""
echo "==> tailing $HOST -> $OUT every ${INTERVAL}s (Ctrl-C to stop)"
trap 'echo; echo "stopped; last snapshot: $OUT/snap-$(printf %04d "$snap")"; exit 0' INT TERM

while :; do
  snap=$((snap + 1))
  d="$OUT/snap-$(printf %04d "$snap")"
  mkdir -p "$d"

  # Size fingerprint first: skip the copy when nothing grew.
  cur="$(ssh -o BatchMode=yes "$HOST" "for f in $FILES; do stat -c '%n %s' \$f 2>/dev/null || echo \"\$f missing\"; done" 2>/dev/null)"

  ssh -o BatchMode=yes "$HOST" '{
    echo "== date/uptime =="; date; cat /proc/uptime
    echo "== pgphoto/polestar =="; ps | grep -E "pgphoto|polestar" | grep -v grep
    echo "== pentax on usb bus =="
    for x in /sys/bus/usb/devices/*; do
      [ -f "$x/idVendor" ] && echo "$(cat $x/idVendor):$(cat $x/idProduct) $(cat $x/product 2>/dev/null)"
    done
    echo "== last camera state (code 286) =="
    sed -r "s/\x1b\[[0-9;]*m//g" /app/Mlog.txt 2>/dev/null | grep -aoE "code\[286\],val\[[^]]*\]" | tail -2
    echo "== crash entries =="
    grep -ac "CRASH sig" /app/stage2-crash.log 2>/dev/null || echo 0
  }' > "$d/state.txt" 2>&1

  for f in $FILES; do
    base="$(basename "$f")"
    ssh -o BatchMode=yes "$HOST" "dd if=$f bs=65536 2>/dev/null" > "$d/$base" 2>/dev/null
  done

  # ANSI stripped copy of the two text logs, for grep-ability.
  for base in Mlog.txt Clog.txt; do
    [ -s "$d/$base" ] && sed -r 's/\x1b\[[0-9;]*m//g' "$d/$base" > "$d/$base.clean" 2>/dev/null
  done

  changed="no"
  [ "$cur" != "$prev" ] && changed="yes"
  prev="$cur"

  # Flag a crash the moment its entry count increases.
  ncrash="$(grep -ac 'CRASH sig' "$d/stage2-crash.log" 2>/dev/null || echo 0)"
  line="$(date -u +%H:%M:%S) snap-$(printf %04d "$snap") changed=$changed crash_entries=$ncrash"
  if [ "$ncrash" -gt "${seen_crash:-0}" ] 2>/dev/null; then
    line="$line  <<< NEW CRASH RECORDED — snapshot $d captures the death scene"
    seen_crash="$ncrash"
  fi
  echo "$line"

  sleep "$INTERVAL"
done
