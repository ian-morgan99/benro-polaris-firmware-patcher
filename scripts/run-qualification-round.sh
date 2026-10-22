#!/bin/bash
# Full qualification round on the installed build.
#
# Three bugs in the previous version of this script cost an entire run; each is
# fixed explicitly here rather than assumed away:
#
#  1. Clog deltas came back zero bytes. The script picked "the newest Clog by
#     name", but the app does not necessarily write the file that sorts last.
#     Fixed by snapshotting the size of EVERY Clog_* and diffing whichever ones
#     actually grew. Clog lines carry no timestamps (#213), so byte-offset
#     attribution is the only reliable method.
#  2. The 40 s shutter index came back as a blob of probe log lines, because the
#     helper printed its transcript to stdout alongside the number. Fixed by
#     emitting the index on a dedicated fd and grepping for a bare integer.
#  3. `--shutter-index` then failed with "invalid int value" for the same reason.
#
# Mode is decided from the camera's own exposure-mode-raw (#206), NOT from the
# shape of the 268 list -- #206 records that heuristic failing in both directions,
# and the reviewer flagged it on #186. Passing --ssh-host also exercises test B1:
# a second gphoto2 session against a camera pgphoto already holds, which has never
# been observed on this hardware.
#
# Exposure duration is read from EXIF afterwards (#186 review): the app's own
# 'bulb time start'..'bulb time end' interval is how long it held the shutter, not
# how long the sensor was exposed.
DEV=192.168.0.1
SSH="ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=8 root@$DEV"
ROOT=/home/ian/Documents/VSCodeProjects/BenroPolarisPatcher
OUT="$ROOT/out/round-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT/dng"
cd "$ROOT" || exit 1
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/RUN.log"; }

snap() {
  timeout 90 $SSH 'cd /app/sd/system/log 2>/dev/null || exit 0
    for f in Clog_*; do [ -f "$f" ] && printf "%s %s\n" "$f" "$(stat -c %s "$f")"; done' \
    2>/dev/null
}
collect_delta() {
  local snapfile="$1" out="$2" f o n
  : > "$out"
  while read -r f o; do
    [ -n "$f" ] || continue
    case "$o" in ''|*[!0-9]*) continue ;; esac
    n=$(timeout 60 $SSH "stat -c %s '/app/sd/system/log/$f'" 2>/dev/null)
    case "$n" in ''|*[!0-9]*) continue ;; esac
    if [ "$n" -gt "$o" ]; then
      echo "### $f offset $o -> $n ($((n-o)) bytes)" >> "$out"
      timeout 90 $SSH "tail -c +$((o+1)) '/app/sd/system/log/$f'" 2>/dev/null >> "$out"
    fi
  done < "$snapfile"
}
card() { timeout 60 $SSH 'echo "count=$(ls /app/sd/normal/ | wc -l) newest=$(ls /app/sd/normal/ | sort | tail -1)"' 2>/dev/null; }

# The camera's own exposure mode, read through the device gphoto2. B = 9.
mode() {
  timeout 60 $SSH 'cd /app; LD_LIBRARY_PATH=/app/lib/stage2:/app/lib \
    CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34 \
    IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2 \
    /app/bin/gphoto2 --get-config pentaxconditions 2>/dev/null' \
    | grep -aoE "exposure-mode-raw=[0-9]+" | head -1
}

run_case() {
  local name="$1"; shift
  log "--- $name ---"
  echo "  mode-before: $(mode)" | tee -a "$OUT/RUN.log"
  local snapfile="$OUT/$name.snap"; snap > "$snapfile"
  timeout 320 python3 scripts/canary-probe.py --ssh-host "root@$DEV" "$@" \
    > "$OUT/$name.log" 2>&1
  grep -aE "DONE|PASS |FAIL|TIMEOUT|TERMINAL|EXPOSURE_MODE|BULB shutter|resolved_shutter" \
    "$OUT/$name.log" | head -8 | tee -a "$OUT/RUN.log"
  sleep 4
  collect_delta "$snapfile" "$OUT/$name.clog.txt"
  echo "  clog delta bytes: $(wc -c < "$OUT/$name.clog.txt")" | tee -a "$OUT/RUN.log"
  grep -aoE "captureBulbImage|capture_image_with_Bulb|Camera-timed Bulb is active|Bulb action requires a readable B|bulb-timer=(yes|no)|bulb time start|bulb time end|capture bulb Image ret [0-9-]+|boundary=camlib-enter|boundary=preconditions-return|boundary=initiate-return|capture wait budget [0-9]+ ms \(exposure phase [0-9]+ ms\)[^|]{0,14}" \
    "$OUT/$name.clog.txt" | sort | uniq -c | tee -a "$OUT/RUN.log"
  card | tee -a "$OUT/RUN.log"
}

log "=== PREFLIGHT ==="
timeout 20 bash -c "</dev/tcp/$DEV/9090" 2>/dev/null || { log "ABORT: device not reachable"; exit 1; }
timeout 90 $SSH 'echo "device_time=$(date +%H:%M:%S) uptime=$(cut -d" " -f1 /proc/uptime)s"
  echo "camera=$(cat /sys/bus/usb/devices/*/product 2>/dev/null | grep -i pentax | head -1)"
  echo "camlib_markers_total=$(cat /app/sd/system/log/Clog_* 2>/dev/null | grep -ac boundary=camlib-enter)"' \
  2>/dev/null | tee -a "$OUT/RUN.log"
# A camera that is present on USB but not claimable must not be recorded as a
# control failure -- a post-reboot run once reported -105 for every command while
# the body was plainly attached.
timeout 90 python3 scripts/canary-probe.py --probe > "$OUT/preflight-probe.log" 2>&1
grep -aE "SUMMARY|CAMERA|FAIL" "$OUT/preflight-probe.log" | head -3 | tee -a "$OUT/RUN.log"
if ! grep -qa "SUMMARY model=" "$OUT/preflight-probe.log"; then
  log "ABORT: camera not usable (no SUMMARY). Not treating this as a control result."
  exit 1
fi
card | tee -a "$OUT/RUN.log"

log "=== STEP 1: bulb 5 s in the CURRENT camera bulb-setting ==="
run_case bulb5 --shot --expected-files 1 --bulb-seconds 5 --shot-timeout 60

log "=== STEP 2: control, ordinary timed capture (no bulb field) ==="
run_case timed6s --shot --expected-files 1 --shot-timeout 60

log "=== STEP 3: 40 s NON-bulb exposure (the #106/#172 budget scenario) ==="
# Emit the index on fd 3 so the probe's transcript cannot contaminate it.
IDX=$(timeout 90 python3 - "$DEV" 3>&1 >/dev/null <<'PY' 2>/dev/null | grep -aE '^[0-9]+$' | tail -1
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("cp", "scripts/canary-probe.py")
cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
p = cp.Polaris(sys.argv[1], 9090, "192.168.0.4", 10.0)
try:
    _, opts = cp.shutter_options(p, quiet=True)
finally:
    p.close()
for i, o in enumerate(opts):
    if o == "00-40":
        os.write(3, f"{i}\n".encode())
        break
PY
)
echo "  resolved 40 s shutter index: '${IDX:-none}'" | tee -a "$OUT/RUN.log"
if [ -n "$IDX" ]; then
  run_case timed40s --shot --expected-files 1 --shutter-index "$IDX" --shot-timeout 200
else
  log "  SKIP: 00-40 not in the shutter list (dial not on a timed mode)"
fi

log "=== STEP 4: retrieve produced DNGs and read EXIF exposure time (#186) ==="
NEWEST=$(timeout 60 $SSH 'ls /app/sd/normal/ | sort | tail -3' 2>/dev/null)
for f in $NEWEST; do
  timeout 180 $SSH "cat '/app/sd/normal/$f'" > "$OUT/dng/$f" 2>/dev/null
done
ls -la "$OUT/dng" | tee -a "$OUT/RUN.log"
timeout 120 python3 scripts/dng-exposure.py "$OUT"/dng/*.dng 2>&1 | tee -a "$OUT/RUN.log"

log "=== STEP 5: mode at end of round (did anything drift?) ==="
echo "  mode-after: $(mode)" | tee -a "$OUT/RUN.log"

log "=== STEP 6: pull device logs before they rotate (#213) ==="
timeout 200 $SSH 'cd /app/sd/system/log; cat Mlog_* Clog_*' > "$OUT/device-logs-full.txt" 2>/dev/null
echo "  saved lines: $(wc -l < "$OUT/device-logs-full.txt")" | tee -a "$OUT/RUN.log"
log "DONE — artefacts in $OUT"
