#!/usr/bin/env bash
# wait-for-camera.sh — block until the attached camera is actually usable, then
# run the command you would have had to re-type by hand.
#
# Every canary/probe script fails immediately when the camera is absent, which
# turns an unattended hardware test into a polling loop you have to babysit.
# This waits on the real precondition (code 286 reporting state:1) and only then
# execs the payload, so a long test started while the camera is asleep or
# unplugged still produces a result.
#
# Usage:
#   scripts/wait-for-camera.sh -- <command...>
#   scripts/wait-for-camera.sh --timeout 2400 --interval 20 -- <command...>
#
# Exit codes:
#   0..255  whatever the payload returned, once the camera was ready
#   201     timed out waiting for the camera (payload never ran)
set -euo pipefail

TIMEOUT=1800
INTERVAL=20
HOST=192.168.0.1
BIND=192.168.0.4
PORT=9090

while [ $# -gt 0 ]; do
  case "$1" in
    --timeout)  TIMEOUT="$2"; shift 2;;
    --interval) INTERVAL="$2"; shift 2;;
    --host)     HOST="$2"; shift 2;;
    --bind)     BIND="$2"; shift 2;;
    --port)     PORT="$2"; shift 2;;
    --)         shift; break;;
    *)          echo "unknown argument: $1" >&2; exit 2;;
  esac
done
[ $# -ge 1 ] || { echo "usage: $0 [--timeout N] -- <command...>" >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROBE="$ROOT/scripts/canary-probe.py"
[ -f "$PROBE" ] || { echo "ERROR: cannot find $PROBE" >&2; exit 2; }

probe_ready() {
  # A single code-286 query. state:1 means the camera is attached and ready;
  # state:-5 / model:none means nothing is on USB. Both are a normal answer, so
  # a transport error and a "not ready" answer are deliberately treated alike.
  python3 - "$HOST" "$PORT" "$BIND" "$PROBE" <<'PY'
import importlib.util, sys
host, port, bind, probe = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("canary_probe", probe)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
try:
    p = mod.Polaris(host, port, bind or None, timeout=8)
except Exception as exc:
    print(f"connect failed: {type(exc).__name__}: {exc}"); raise SystemExit(1)
try:
    p.send(284); p.wait_code(284, 5)
    p.send(286); cam = p.wait_code(286, 10)
    state = mod.field(cam, "state")
    print(f"286 -> {cam}")
    raise SystemExit(0 if state == "1" else 1)
except SystemExit:
    raise
except Exception as exc:
    print(f"probe failed: {type(exc).__name__}: {exc}"); raise SystemExit(1)
finally:
    p.close()
PY
}

echo "$(date -u +%FT%TZ) [wait-for-camera] waiting for camera state:1 (timeout ${TIMEOUT}s, poll ${INTERVAL}s)"
deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  if out=$(probe_ready 2>&1); then
    echo "$(date -u +%FT%TZ) [wait-for-camera] camera ready: $out"
    echo "$(date -u +%FT%TZ) [wait-for-camera] exec: $*"
    exec "$@"
  fi
  echo "$(date -u +%FT%TZ) [wait-for-camera] not ready: $(printf '%s' "$out" | tail -1)"
  [ "$(date +%s)" -lt "$deadline" ] || { echo "$(date -u +%FT%TZ) [wait-for-camera] TIMED OUT"; exit 201; }
  sleep "$INTERVAL"
done
