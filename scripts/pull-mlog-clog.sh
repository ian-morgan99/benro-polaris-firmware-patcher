#!/usr/bin/env bash
# pull-mlog-clog.sh — pull Mlog/Clog + device state from a Benro Polaris gimbal.
#
# Run this on the machine that is joined to the gimbal's own AP (polaris_d13e86,
# BSSID prefix 48:E7:DA). The gimbal answers at root@192.168.0.1 — but so does
# your home router, so the script verifies device identity before trusting
# anything (see .github/skills/polaris-debugging/SKILL.md §2).
#
# Usage:
#   ./scripts/pull-mlog-clog.sh [user@host] [output-dir]
#   ./scripts/pull-mlog-clog.sh root@192.168.0.1 /tmp/polaris-logs
#
# Output: <output-dir>/polaris-logs-<timestamp>.tar.gz containing:
#   meta.txt          — identity check, FwVer, provenance, uptime, ps, mounts
#   system-log/       — every Mlog_*/Clog_* (and any other) log on the SD card
#   sd-root-listing   — what is at the SD root (FwPkt staging state)
set -euo pipefail

HOST="${1:-root@192.168.0.1}"
OUTDIR="${2:-/tmp/polaris-logs}"
TS="$(date -u +%Y%m%d-%H%M%S)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$OUTDIR"

echo "==> 1/4 identity check (must be the gimbal, not the router)..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  'cat /app/FwVer; ls /app/bin/polestar_app /app/bin/pgphoto' || {
    echo "FAILED: $HOST is not answering like a Polaris gimbal." >&2
    echo "  - Are you joined to the polaris_* AP (BSSID 48:E7:DA...), not your home Wi-Fi?" >&2
    echo "  - Is the gimbal awake? (BT wake per .github/skills/fwpkt-update-flow/SKILL.md)" >&2
    exit 1
}

echo "==> 2/4 collecting device state..."
ssh -o BatchMode=yes "$HOST" '
set -u
{
  echo "== identity =="
  cat /app/FwVer
  uname -a
  uptime
  echo "== provenance =="
  cat /app/openpolaris-libgphoto2-provenance.txt 2>/dev/null || echo "(no provenance file)"
  echo "== processes =="
  ps | grep -E "polestar|pgphoto" | grep -v grep
  echo "== mounts (SD card) =="
  cat /proc/mounts | grep -E "mmcblk|/app/sd" || true
  echo "== sd root =="
  ls -la /app/sd 2>/dev/null || echo "(SD not mounted at /app/sd)"
} > "$1/meta.txt" 2>&1
' "$STAGE"

echo "==> 3/4 pulling Mlog/Clog from the SD card..."
ssh -o BatchMode=yes "$HOST" '
set -u
mkdir -p "$1/system-log"
if [ -d /app/sd/system/log ]; then
  # newest 25 of each kind — enough for any recent session, small enough to scp fast
  ls -t /app/sd/system/log/Mlog_* 2>/dev/null | head -25 | while read -r f; do cp "$f" "$1/system-log/"; done
  ls -t /app/sd/system/log/Clog_* 2>/dev/null | head -25 | while read -r f; do cp "$f" "$1/system-log/"; done
  # any other log kinds present (access/error/etc.)
  for f in /app/sd/system/log/*; do
    b=$(basename "$f")
    case "$b" in Mlog_*|Clog_*) ;; *) [ -f "$f" ] && cp "$f" "$1/system-log/" ;; esac
  done
else
  echo "SD card log dir /app/sd/system/log not found — is the card in the gimbal?" > "$1/system-log/MISSING.txt"
fi
ls -la /app/sd > "$1/sd-root-listing" 2>&1 || true
' "$STAGE"

echo "==> 4/4 packaging..."
tar czf "$OUTDIR/polaris-logs-$TS.tar.gz" -C "$STAGE" .
echo "OK: $OUTDIR/polaris-logs-$TS.tar.gz ($(du -h "$OUTDIR/polaris-logs-$TS.tar.gz" | cut -f1))"
echo "Drop it into docs/evidence/ (or hand it to the agent) with a note of what you were doing when the problem happened."
