#!/usr/bin/env bash
# Measure the camera gate on a clean, fully-initialised head.
#
# pgphoto binds the USB camera during its boot-time session setup. Killing and
# relaunching it by hand leaves the process running but never bound -- 286 answers
# model:none;state:-2 and every config read then blocks until its deadline, which
# looks exactly like the admission-gate wedge being measured. So a trustworthy
# A/B has to reboot between loader swaps, not just restart the process.
#
#   gate-ab.sh <loader.so> <label>
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${STAGE2_HOST:-root@192.168.0.1}"
DIR="/app/lib/stage2"
LIVE="$DIR/libpolaris_stage2.so"
BAK="$DIR/libpolaris_stage2.so.pre-hotswap"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=25 $HOST"

LOADER="${1:?usage: gate-ab.sh <loader.so> <label>}"
LABEL="${2:-candidate}"
[ -f "$LOADER" ] || { echo "no such file: $LOADER" >&2; exit 1; }

echo "=== $LABEL: installing $(basename "$LOADER") ==="
$SSH "[ -f $BAK ] || cp -a $LIVE $BAK"
cat "$LOADER" | $SSH "cat > $LIVE.new && chmod 755 $LIVE.new && mv $LIVE.new $LIVE && md5sum $LIVE"

echo "=== $LABEL: rebooting for a clean camera session ==="
$SSH 'nohup sh -c "sleep 1; reboot" >/dev/null 2>&1 &'
for i in $(seq 1 30); do
    sleep 10
    if $SSH 'echo up' 2>/dev/null | grep -q up; then
        echo "ssh back after ~$((i*10))s"
        break
    fi
done

# pgphoto initialises the session during boot; give it time, then require that
# the head actually reports a bound camera before measuring anything.
for i in $(seq 1 12); do
    sleep 5
    if $SSH 'sed "s/\x1b\[[0-9;]*m//g" /app/Clog.txt | grep -aq "model:pentax k-1 mark ii"' ; then
        echo "camera session established after ~$((i*5))s more"
        break
    fi
done

echo "=== $LABEL: state ==="
$SSH 'md5sum /app/lib/stage2/libpolaris_stage2.so
for p in $(ls /proc | grep -E "^[0-9]+$"); do
    [ "$(readlink /proc/$p/exe 2>/dev/null)" = "/app/lib/stage2/pgphoto.stage2ondisk" ] && \
        echo "pid=$p usb_fds=$(ls -l /proc/$p/fd 2>/dev/null | grep -c bus/usb) threads=$(ls /proc/$p/task | wc -l)"
done
sed "s/\x1b\[[0-9;]*m//g" /app/Clog.txt | grep -ac "admission refused" | sed "s/^/refusals_so_far=/"'

echo "=== $LABEL: stress ==="
python3 "$HERE/stress-config-gate.py" --clients 8 --rounds 6 --quiet 2>&1 | tail -9
