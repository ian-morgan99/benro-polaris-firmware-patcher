#!/usr/bin/env bash
# Capture a Benro Connect session so the evidence SURVIVES an app crash.
#
# Why this exists (issue #241): polestar_app truncates /app/Mlog.txt and
# /app/Clog.txt on restart, without a reboot. Every crash therefore erases its
# own evidence, and by the time we can SSH in the logs are 0 bytes. The only
# session we have ever analysed (Oct 10) survived purely by luck of rotation.
#
# This script tails both device-side logs into host-side files for the whole
# test session. The host copy is written continuously, so it is intact even if
# the app dies and the device truncates its own copies a second later.
#
# usage: capture-crash-session.sh [device-ip] [label]
#   then reproduce the crash in Benro Connect, then Ctrl-C here.
set -uo pipefail

IP="${1:-192.168.0.1}"
LABEL="${2:-session-$(date +%Y%m%d-%H%M%S)}"

# tools/host-bin provides the docker/ssh helpers this repo relies on.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PATH="$ROOT/tools/host-bin:$PATH"

# Absolute: the script must work no matter where it is invoked from, and the
# evidence belongs in the repo regardless of CWD.
OUT="$ROOT/docs/evidence/crash-capture-$LABEL"
mkdir -p "$OUT"

command -v ssh >/dev/null 2>&1 || { echo "ssh not found" >&2; exit 1; }

echo "=== capture-crash-session.sh ==="
echo "device: $IP"
echo "output: $OUT/"

# Record the starting state so we can tell truncation from rotation later.
ssh -o BatchMode=yes "root@$IP" '
  date
  cat /proc/uptime | cut -d" " -f1
  cat /app/FwVer 2>/dev/null
  ls -la /app/Mlog.txt /app/Clog.txt 2>/dev/null
  ps -o pid,etime,args 2>/dev/null | grep -E "polestar_app|pgphoto" | grep -v grep
' > "$OUT/session-start.txt" 2>&1
sed 's/^/  /' "$OUT/session-start.txt"

echo
echo "Tailing device logs. Reproduce the crash in Benro Connect now."
echo "Press Ctrl-C when done."
echo

# Two independent tails: if one connection drops the other keeps going, and a
# truncation on the device shows up here as the stream stopping, not vanishing.
#
# -F follows by NAME and re-opens after a truncate, which is exactly the failure
# mode in #241 -- polestar_app truncates the file on restart. -n 500 pulls a
# backlog first so we still have context if the crash happens moments after
# this script starts.
ssh -o BatchMode=yes -o ServerAliveInterval=10 "root@$IP" 'tail -n 500 -F /app/Mlog.txt' \
  > "$OUT/Mlog.txt" 2>"$OUT/Mlog.err" &
PID_M=$!
ssh -o BatchMode=yes -o ServerAliveInterval=10 "root@$IP" 'tail -n 500 -F /app/Clog.txt' \
  > "$OUT/Clog.txt" 2>"$OUT/Clog.err" &
PID_C=$!

cleanup() {
  echo
  echo "Stopping capture..."
  kill "$PID_M" "$PID_C" 2>/dev/null
  wait "$PID_M" "$PID_C" 2>/dev/null
  # Final state: compare against session-start to prove truncation happened.
  ssh -o BatchMode=yes "root@$IP" '
    date
    cat /proc/uptime | cut -d" " -f1
    ls -la /app/Mlog.txt /app/Clog.txt 2>/dev/null
    ps -o pid,etime,args 2>/dev/null | grep -E "polestar_app|pgphoto" | grep -v grep
  ' > "$OUT/session-end.txt" 2>&1
  wc -l "$OUT/Mlog.txt" "$OUT/Clog.txt" > "$OUT/line-counts.txt" 2>&1
  echo "captured: $(cat "$OUT/line-counts.txt" | tr '\n' ' ')"
  echo "If the device-side files are now smaller than these host copies, that is"
  echo "the truncation-on-restart described in #241."
  exit 0
}
trap cleanup INT TERM

wait
