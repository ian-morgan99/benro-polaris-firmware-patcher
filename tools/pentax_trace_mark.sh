#!/bin/sh
# Minimal dependency-free helper for embedded Polaris instrumentation.
# Usage: pentax_trace_mark.sh FILE RUN_ID EXPERIMENT EVENT PHASE [DETAIL]
set -eu

FILE="$1"
RUN_ID="$2"
EXPERIMENT="$3"
EVENT="$4"
PHASE="$5"
DETAIL="${6:-}"

# Prefer monotonic data from /proc/uptime on constrained firmware. This is an
# observation helper only; it must never make camera-control decisions.
UPTIME="$(cut -d' ' -f1 /proc/uptime 2>/dev/null || echo unknown)"
WALL="$(date +%s 2>/dev/null || echo unknown)"
PID="$$"

# DETAIL is escaped conservatively for a single JSON string field.
ESCAPED_DETAIL="$(printf '%s' "$DETAIL" | sed 's/\\/\\\\/g; s/"/\\"/g')"
mkdir -p "$(dirname "$FILE")"
printf '{"run_id":"%s","experiment":"%s","event":"%s","phase":"%s","uptime_s":"%s","wall_s":"%s","observer_pid":%s,"detail":"%s"}\n' \
  "$RUN_ID" "$EXPERIMENT" "$EVENT" "$PHASE" "$UPTIME" "$WALL" "$PID" "$ESCAPED_DETAIL" >> "$FILE"
