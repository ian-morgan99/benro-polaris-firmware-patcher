#!/bin/sh
set -eu

# Offline regression test for scripts/keep-lv-ab.py's analyser and verdict, using
# synthetic logs so no hardware is needed. The analyser is the part that decides
# whether a run "survived", so it must not silently miscount: on the real session
# 34 logs it correctly reports the recovered removal as six uevents and the fatal
# one as two, which is the physical clue #347 now hinges on.

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
AB=$ROOT/scripts/keep-lv-ab.py
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

mkdir -p "$TMP/logs"

# Healthy teardown: interface uevents then the device (six lines).
cat > "$TMP/logs/Mlog_000001.log" <<'EOF'
[10:00:00:100 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2:1.0/video4linux/video0
[10:00:00:110 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2:1.0/input/input0/event0
[10:00:00:120 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2:1.0/input/input0
[10:00:00:130 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2:1.0
[10:00:00:140 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2:1.1
[10:00:00:150 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2
EOF

# Fatal teardown: truncated after two lines, plus a sustained preview stream and
# the camera present earlier in the session. The presence marker is the one the
# real logs use -- `manufacturer:ricoh imaging company` -- not "pentax".
cat > "$TMP/logs/Clog_000001.log" <<'EOF'
[09:59:00:000 INFO-]:send_ipc_msg_retry[80]:SP_sendMsg success; id[98307] type[1],code[286],val[manufacturer:ricoh imaging company;model:K-3 III]
Pentax preview stage get-frame returned 0x2001 (73189 bytes, 1 attempts, 16 ms).
Pentax preview stage get-frame returned 0x2001 (73189 bytes, 1 attempts, 16 ms).
Pentax preview stage get-frame returned 0x2001 (73189 bytes, 1 attempts, 16 ms).
[10:00:05:100 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2/1-1.2:1.0
[10:00:05:150 INFO-]:NetlinkUeventTask[65]:info:remove@/devices/platform/soc/100e0000.xhci_0/usb1/1-1/1-1.2
EOF

# A session where the body was never attached: only the absent marker, so it must
# not be scored as "camera seen".
mkdir -p "$TMP/none"
cat > "$TMP/none/Clog_000002.log" <<'EOF'
[11:00:00:000 INFO-]:send_ipc_msg_retry[80]:SP_sendMsg success; id[98307] type[1],code[286],val[manufacturer:none;model:none]
EOF

python3 - "$AB" "$TMP/logs" <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("ab", sys.argv[1])
ab = importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)
r = ab.analyse(sys.argv[2])
assert r["camera_seen"], "camera present in logs must be detected"
assert r["frames"] == 3, f"frame count wrong: {r['frames']}"
eps = {(e["t"], e["n"]) for e in r["removal_episodes"]}
assert eps == {("10:00:00", 6), ("10:00:05", 2)}, f"episodes wrong: {eps}"
assert r["truncated_removals"] == 1, f"truncated count wrong: {r['truncated_removals']}"
n = ab.analyse(os.path.join(sys.argv[2], "none"))
assert not n["camera_seen"], "manufacturer:none must NOT count as a camera present"
print("ok analyser: counts frames, detects camera, flags the truncated removal")
PY

# Verdict logic: refuses to over-claim, and names the right follow-up.
python3 - "$AB" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("ab", sys.argv[1])
ab = importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)

def rows(on_survives, off_survives, n=3):
    out = []
    for i in range(n):
        out.append({"arm": "keep-on",  "run": i+1, "camera_after": on_survives})
        out.append({"arm": "keep-off", "run": i+1, "camera_after": off_survives})
    return out

assert "INCOMPLETE" in ab.verdict([])
assert "IMPLICATED" in ab.verdict(rows(False, True))
assert "NOT IMPLICATED" in ab.verdict(rows(True, True))
assert "BOTH FAIL" in ab.verdict(rows(False, False))
assert "MIXED" in ab.verdict(rows(True, False))
# A single surviving run must not outvote the failures.
mixed = [{"arm":"keep-on","run":1,"camera_after":False},
         {"arm":"keep-on","run":2,"camera_after":True},
         {"arm":"keep-off","run":1,"camera_after":True}]
assert "IMPLICATED" in ab.verdict(mixed)

# The default run is keep-on ONLY, because the teardown arm is the one that
# machine-gunned the shutter. A single-arm result must still be interpretable.
on_only_fail = [{"arm":"keep-on","run":1,"camera_after":False}]
assert "REPRODUCED" in ab.verdict(on_only_fail)
assert "repeat" in ab.verdict([{"arm":"keep-on","run":1,"camera_after":True}])

# The shutter tripwire outranks every other outcome, including a clean pass.
tripped = [{"arm":"keep-on","run":1,"camera_after":True,"aborted":"NEW CARD IMAGE"}]
assert "SHUTTER TRIPWIRE" in ab.verdict(tripped)
tripped2 = rows(True, True) + [{"arm":"keep-off","run":9,"camera_after":True,
                                "aborted":"NEW CARD IMAGE after request 4"}]
assert "SHUTTER TRIPWIRE" in ab.verdict(tripped2)

# The hazardous arm must not be reachable without an explicit opt-in.
assert ab.ARM_ON == ("keep-on", "1") and ab.ARM_OFF == ("keep-off", "0")
print("ok verdict: all outcomes, single-arm runs, and the shutter tripwire wins")
PY

# The default plan must NOT include the keep-off (per-frame teardown) arm.
OUT=$(python3 "$AB" --plan)
printf '%s\n' "$OUT" | grep -q 'arm keep-on'
printf '%s\n' "$OUT" | grep -q 'keep-off arm SKIPPED by default'
printf '%s\n' "$OUT" | grep -q 'COUNT-capped, never time-based'
# And it must be opt-in only.
printf '%s\n' "$(python3 "$AB" --plan --run-teardown-arm)" | grep -q 'arm keep-off'

echo 'PASS: keep-lv A/B analyser counts frames/uevents and verdicts without over-claiming (issue #347)'
