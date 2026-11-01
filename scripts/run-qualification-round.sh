#!/bin/bash
# Full qualification round on the installed build.
#
# #203 rewrote this runner's verdict handling. The previous version could print
# `DONE — artefacts in ...` after failures inside the round, because it discarded
# every probe exit code and assembled its result by grepping PASS/FAIL strings.
# A round is now fail-closed: each case contributes one machine-readable result
# line, and scripts/qualification-verdict.py decides the gate. Its exit code is
# this script's exit code.
#
# What that means in practice:
#   * a probe failure, timeout or crash is a FAIL, never a missing line;
#   * a case whose precondition cannot be verified is an ERROR, not a pass;
#   * a SKIP needs a machine-evaluated reason (e.g. the camera's own shutter list
#     has no such slot) and yields exit 2 — qualified with gaps, not clean;
#   * every file a case produced is correlated to that case and its EXIF
#     ExposureTime is compared with the exposure the case claims (#186: an
#     app-measured hold is not a sensor exposure);
#   * the preflight must prove a capture is claimable, not just that a model
#     string came back.
#
# Three older bugs that cost an entire run stay fixed here:
#   1. Clog deltas came back zero bytes because the script picked "the newest
#      Clog by name"; the app does not necessarily write the file that sorts
#      last. Fixed by snapshotting the size of EVERY Clog_* and diffing whichever
#      ones grew. Clog lines carry no timestamps (#213), so byte-offset
#      attribution is the only reliable method.
#   2/3. Shutter index values used to be scraped from probe stdout, which mixed
#      log lines into the number. No longer needed: the probe resolves and sets
#      the shutter itself (--timed-seconds) and reports it in its result JSON.
#
# Mode comes from the camera's own exposure-mode-raw (#206), never from the shape
# of the 268 list — #206 records that heuristic failing in both directions.
#
# Deliberately NOT `set -e`: a transient SSH or grep failure must not abort the
# round and destroy the evidence for the cases that already ran. Every step that
# matters checks its own status, and the verdict is computed at the end.
set -uo pipefail

DEV=192.168.0.1
SSH="ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=8 root@$DEV"
# Resolve the checkout from this script, rather than silently switching to an
# unrelated clone. This matters when the release candidate was built from a
# clean worktree such as /home/ian/polaris-build-73.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/round-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT/dng" "$OUT/results"
cd "$ROOT" || exit 1
RESULTS="$OUT/results.jsonl"
: > "$RESULTS"
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

# Full card listing, so files created during a case can be attributed to it.
card_listing() {
  timeout 60 $SSH 'ls /app/sd/normal/ 2>/dev/null | sort' 2>/dev/null
}
card() {
  timeout 60 $SSH 'echo "count=$(ls /app/sd/normal/ 2>/dev/null | wc -l) newest=$(ls /app/sd/normal/ 2>/dev/null | sort | tail -1)"' 2>/dev/null
}

# The camera's own exposure mode, read through the device gphoto2. B = 9.
mode() {
  timeout 60 $SSH 'cd /app; LD_LIBRARY_PATH=/app/lib/stage2:/app/lib \
    CAMLIBS=/app/lib/stage2/libgphoto2/2.5.34 \
    IOLIBS=/app/lib/stage2/libgphoto2_port/0.12.2 \
    /app/bin/gphoto2 --get-config pentaxconditions 2>/dev/null' \
    | grep -aoE "exposure-mode-raw=[0-9]+" | head -1
}

# Pull the produced files for one case and read their EXIF exposure. Returns the
# first ExposureTime found, or nothing when no file carries one — the verdict
# treats a missing value as an unsupported claim rather than silence.
case_exposure() {
  local f base et=""
  for f in "$@"; do
    base=$(basename "$f")
    timeout 180 $SSH "cat '$f'" > "$OUT/dng/$base" 2>/dev/null
    if [ ! -s "$OUT/dng/$base" ]; then
      echo "  dng: $base could not be retrieved" | tee -a "$OUT/RUN.log"
      continue
    fi
    et=$(timeout 120 python3 scripts/dng-exposure.py "$OUT/dng/$base" 2>/dev/null \
         | grep -oE '\(([0-9]+\.[0-9]+) s\)' | head -1 | tr -dc '0-9.')
    [ -n "$et" ] && break
  done
  printf '%s' "$et"
}

# One case: run it, capture the probe's exit code and structured result, and
# append a single verdict line. Never aborts the round.
run_case() {
  local name="$1"; shift
  log "--- $name ---"
  local snapfile="$OUT/$name.snap"; snap > "$snapfile"
  local before="$OUT/$name.card-before" after="$OUT/$name.card-after"
  card_listing > "$before"
  local rj="$OUT/results/$name.json"
  local rc=0
  timeout 420 python3 scripts/canary-probe.py --ssh-host "root@$DEV" \
    --require-exposure-mode --result-json "$rj" "$@" > "$OUT/$name.log" 2>&1 || rc=$?
  echo "  probe rc=$rc" | tee -a "$OUT/RUN.log"
  grep -aE "TIMED|BULB|SHUTTER_OPTIONS|PRECONDITION|PASS |TIMEOUT|TERMINAL|EXPOSURE_MODE" \
    "$OUT/$name.log" | head -8 | tee -a "$OUT/RUN.log"

  sleep 4
  collect_delta "$snapfile" "$OUT/$name.clog.txt"
  echo "  clog delta bytes: $(wc -c < "$OUT/$name.clog.txt")" | tee -a "$OUT/RUN.log"

  # Correlate every newly created card file to this case (#203). The probe also
  # reports the files it saw; anything on the card that it did not report is
  # recorded so an unattributed capture cannot pass unnoticed.
  card_listing > "$after"
  local newfiles
  newfiles=$(comm -13 "$before" "$after" | sed 's|^|/app/sd/normal/|')
  if [ -n "$newfiles" ]; then
    echo "  card files created by this case:" | tee -a "$OUT/RUN.log"
    echo "$newfiles" | sed 's/^/    /' | tee -a "$OUT/RUN.log"
  fi

  local et=""
  if [ -n "$newfiles" ]; then
    et=$(case_exposure "$name" $newfiles)
    [ -n "$et" ] && echo "  EXIF exposure_time=${et}s" | tee -a "$OUT/RUN.log"
  fi

  python3 - "$name" "$rc" "$rj" "$et" "$newfiles" >> "$RESULTS" <<'PY'
import json, sys
name, rc, path, et, newfiles = sys.argv[1:6]
try:
    with open(path) as handle:
        result = json.load(handle)
except (OSError, ValueError) as exc:
    # No result file means the probe died before it could report anything. That
    # is an ERROR, not a skip: the case ran and its outcome is unknown.
    print(json.dumps({"case": name, "status": "error", "rc": int(rc),
                      "reason": f"no result JSON ({type(exc).__name__}: {exc})"}))
    sys.exit(0)
result["case"] = name
result["rc"] = int(rc)
if et:
    result["actual_exposure_s"] = float(et)
card_files = [line for line in newfiles.splitlines() if line.strip()]
reported = list(result.get("files") or [])
extra = [f for f in card_files if f not in reported]
if extra:
    result["unattributed_files"] = extra
# Trust the probe's status only when it agrees with its exit code.
if int(rc) == 0 and result.get("status") != "pass":
    result["status"] = "error"
    result["reason"] = f"probe exited 0 but reported status={result.get('status')!r}"
elif int(rc) != 0 and result.get("status") == "pass":
    result["status"] = "error"
    result["reason"] = f"probe reported pass but exited {rc}"
print(json.dumps(result))
PY
  sleep 4
}

# Machine-evaluated applicability: ask the camera what shutter slots exist, so a
# case that cannot be run is a reasoned SKIP rather than a silent omission.
shutter_slots() {
  timeout 90 python3 scripts/canary-probe.py --list-shutters 2>/dev/null \
    | grep -a '^SHUTTERS_JSON ' | sed 's/^SHUTTERS_JSON //'
}
has_slot() {
  local want="$1" json="$2"
  [ -n "$json" ] || return 1
  printf '%s' "$json" | python3 -c '
import json, sys
want = float(sys.argv[1])
try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
for entry in data.get("slots", []):
    seconds = entry.get("seconds")
    if seconds is not None and abs(float(seconds) - want) < 1e-6:
        sys.exit(0)
sys.exit(1)' "$want"
}

record_skip() {
  python3 -c '
import json, sys
print(json.dumps({"case": sys.argv[1], "status": "skip", "reason": sys.argv[2]}))
' "$1" "$2" >> "$RESULTS"
  log "SKIP $1: $2"
}

log "=== STEP 0: preflight — prove a capture is claimable ==="
# A camera that answers with a model string but cannot be captured from must not
# produce a round full of control failures. Require the camera to report itself
# attached (code 286 state=1), not merely to answer at all.
if ! timeout 90 python3 scripts/canary-probe.py --probe > "$OUT/preflight-probe.log" 2>&1; then
  log "ABORT: preflight probe failed (see preflight-probe.log). No control results recorded."
  exit 1
fi
grep -aE "SUMMARY|CAMERA" "$OUT/preflight-probe.log" | head -3 | tee -a "$OUT/RUN.log"
if ! grep -qa "state=1" "$OUT/preflight-probe.log"; then
  log "ABORT: camera not in the attached state (code 286 state!=1). Not a control result."
  exit 1
fi
SHUTTERS=$(shutter_slots)
if [ -z "$SHUTTERS" ]; then
  log "ABORT: could not read the live shutter list. Applicability cannot be evaluated."
  exit 1
fi
echo "  shutter slots: $(printf '%s' "$SHUTTERS" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("slots",[])), "slots; model=", d.get("model"), "bulb_list=", d.get("bulb_slot_list"))')" | tee -a "$OUT/RUN.log"
echo "  mode-before-round: $(mode)" | tee -a "$OUT/RUN.log"
card | tee -a "$OUT/RUN.log"

log "=== STEP 1: bulb 5 s in the CURRENT camera bulb-setting ==="
run_case bulb5 --shot --expected-files 1 --bulb-seconds 5 --shot-timeout 60

log "=== STEP 2: control, ordinary timed capture on a verified 6 s shutter ==="
# --timed-seconds resolves 6 s against the live list, writes it through 261 and
# polls the readback before capturing. If no slot is exactly 6 s the probe fails
# rather than shooting some other duration under a `timed6s` label (#203).
if has_slot 6 "$SHUTTERS"; then
  run_case timed6s --shot --expected-files 1 --timed-seconds 6 --shot-timeout 90
else
  record_skip timed6s "camera's command-268 list has no exact 6 s slot"
fi

log "=== STEP 3: 40 s NON-bulb exposure (the #106/#172 budget scenario) ==="
if has_slot 40 "$SHUTTERS"; then
  run_case timed40s --shot --expected-files 1 --timed-seconds 40 --shot-timeout 150
else
  record_skip timed40s "camera's command-268 list has no exact 40 s slot"
fi

log "=== STEP 4: mode at end of round (did anything drift?) ==="
echo "  mode-after-round: $(mode)" | tee -a "$OUT/RUN.log"

log "=== STEP 5: pull device logs before they rotate (#213) ==="
timeout 200 $SSH 'cd /app/sd/system/log; cat Mlog_* Clog_*' > "$OUT/device-logs-full.txt" 2>/dev/null
echo "  saved lines: $(wc -l < "$OUT/device-logs-full.txt")" | tee -a "$OUT/RUN.log"

log "=== STEP 6: verdict ==="
python3 scripts/qualification-verdict.py --results-file "$RESULTS" | tee -a "$OUT/RUN.log"
VERDICT=${PIPESTATUS[0]}
case "$VERDICT" in
  0) log "QUALIFIED — artefacts in $OUT" ;;
  2) log "QUALIFIED WITH GAPS — see SKIP lines above; artefacts in $OUT" ;;
  *) log "NOT QUALIFIED — see PROBLEM lines above; artefacts in $OUT" ;;
esac
exit "$VERDICT"
