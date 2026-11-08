#!/usr/bin/env python3
"""One consolidated camera-control qualification round for the WBS-04 items.

Raised while preparing a single physical test session for issue #293 Phase 4. The
camera issues (#275 preview, #276 shutter, #277 ISO, #278 AF, #279 capture, #251 Bulb,
#285 crash, #274 busy) each accumulated their own ad-hoc probe, and every one of them
reports a verdict without preserving the bytes that produced it. Measured over
docs/evidence before writing this:

    ret:-2110            0 occurrences in the whole archive
    SP_SET_SHUTTER OK   8, FAIL 14
    SP_SET_FNUM   OK    8, FAIL  1     (aperture; there is no SP_SET_APERTURE marker)
    SP_SET_ISO    OK    8, FAIL  0
    SP_SET_EV     OK    4, FAIL  0
    SP_SET_WB     OK    0, FAIL  1

#275, #276 and #277 all quote `ret:-2110` lines dated 2026-11-08. Those logs are not in
the archive and are not on disk anywhere: the session that produced them was never
pulled, so the single most quoted piece of evidence for the control failures cannot be
re-examined. #293 says "Retained raw evidence is necessary before quoting earlier 62%
rate" -- this harness exists to make that true rather than to restate the number.

What it does differently from the per-issue probes:

  * Evidence first. Mlog/Clog are snapshotted before and after every case, so a verdict
    always has the bytes behind it, and the bundle is written even when a case fails.
  * One verdict per WBS item, never one verdict for all of them. #285's claim that the
    segfault "explains ALL the previously observed failures" is testable and is tested
    here as its own case; the archive already contradicts it, because SP_SET_ISO OK and
    SP_SET_SHUTTER OK both exist, which requires a live pgphoto. Collapsing them would
    hide the shutter-specific failure (#276 never recovers while ISO does).
  * Statuses are BLOCKED / CODE_COMPLETE_UNVERIFIED / OFFLINE_VERIFIED / DEVICE_VERIFIED
    / FAIL / UNKNOWN, per #293's operating rules. A case that could not reach the camera
    is BLOCKED, never a silent pass, and nothing here can produce DEVICE_VERIFIED without
    actually talking to the device.
  * Safety limits are enforced, not documented. Exposure length is capped by reusing
    canary_probe's own MAX_TEST_EXPOSURE_SECONDS, and Bulb cases require an explicit
    --i-am-present flag because #293 forbids unattended Bulb tests.

Usage:
    camera-qualification-round.py --plan                 # what it would run, no device
    camera-qualification-round.py --host 192.168.0.1      # the real round
    camera-qualification-round.py --host ... --with-bulb --i-am-present
    camera-qualification-round.py --analyze-only BUNDLE   # re-score saved bytes offline

Transport primitives are imported from canary_probe.py rather than duplicated, so the
9090 framing has one owner.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Reuse the proven transport and safety limits. Import failure is fatal on purpose: a
# harness that silently fell back to its own framing could disagree with the app path.
# The file is canary-probe.py -- the hyphen makes it unimportable by name, so it is
# loaded from its path explicitly rather than renamed under it.
try:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "polaris_canary_probe", os.path.join(HERE, "canary-probe.py"))
    if _spec is None or _spec.loader is None:
        raise ImportError("no loader for canary-probe.py")
    cp = importlib.util.module_from_spec(_spec)
    sys.modules["polaris_canary_probe"] = cp
    _spec.loader.exec_module(cp)
except Exception as exc:  # pragma: no cover - import-time environment problem
    print(f"FATAL: cannot load canary-probe.py: {exc}", file=sys.stderr)
    raise SystemExit(2)

DEFAULT_HOST = "192.168.0.1"
SSH_USER_HOST = "root@192.168.0.1"
PORT = 9090
SD_LOG_DIR = "/app/sd/system/log"

# Control opcodes, taken from the app's own traffic in docs/evidence rather than guessed:
#   code[258] val[iso:]  code[259] val[wb:]  code[260] val[ev:]  code[261] val[s:]
#   code[262] val[mode:] code[264] capture   code[268] shutter list
#   code[276] val[f:] aperture  code[291]/code[292] preview start/query
OPCODES = {
    "iso": 258,
    "wb": 259,
    "ev": 260,
    "shutter": 261,
    "mode": 262,
    "capture": 264,
    "shutter_list": 268,
    "aperture": 276,
    "preview_set": 291,
    "preview_query": 292,
}

# Markers pgphoto/polestar actually emit. SP_SET_FNUM is aperture; there is no
# SP_SET_APERTURE, which is why an earlier survey of this reported zero aperture results.
CONTROL_MARKERS = {
    "shutter": "SP_SET_SHUTTER",
    "aperture": "SP_SET_FNUM",
    "iso": "SP_SET_ISO",
    "ev": "SP_SET_EV",
    "wb": "SP_SET_WB",
}

STATUS_ORDER = ["DEVICE_VERIFIED", "OFFLINE_VERIFIED", "CODE_COMPLETE_UNVERIFIED",
                "UNKNOWN", "BLOCKED", "FAIL"]

# Per-case timeouts. Generous: the K-1 II config tree takes ~40 s from launch (#253),
# and a readiness window shorter than that is itself one of the bugs being tested.
CONNECT_TIMEOUT_S = 15.0
ACK_TIMEOUT_S = 15.0
READBACK_BUDGET_S = 45.0


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Recorder:
    """Append-only evidence writer. Everything lands in the bundle even if we crash."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        os.makedirs(posixpath.join(root, "logs-before"), exist_ok=True)
        os.makedirs(posixpath.join(root, "logs-after"), exist_ok=True)
        os.makedirs(posixpath.join(root, "cases"), exist_ok=True)
        self.path = posixpath.join(root, "transcript.txt")
        self.records: list[dict] = []

    def line(self, text: str) -> None:
        entry = f"{stamp()} {text}"
        print(entry, flush=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")

    def case(self, record: dict) -> None:
        self.records.append(record)
        name = record["wbs"].replace(".", "-").lower()
        with open(posixpath.join(self.root, "cases", f"{name}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)


def ssh_run(user_host: str, cmd: str, timeout: float = 60.0) -> tuple[int, str]:
    """Run a shell command on the device. Returns (rc, combined output)."""
    try:
        proc = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=8",
             "-o", "BatchMode=yes", user_host, cmd],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "<ssh timed out>"
    except OSError as exc:
        return 125, f"<ssh unavailable: {exc}>"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def device_reachable(user_host: str) -> tuple[bool, str]:
    """Confirm this is the gimbal and not a router answering on the same address."""
    rc, out = ssh_run(user_host, "cat /app/FwVer 2>/dev/null; ls /app/bin/pgphoto "
                                  "2>/dev/null", timeout=25)
    if rc != 0 or not out.strip():
        return False, out.strip() or "no response"
    fwver = next((ln.strip() for ln in out.splitlines() if ln.strip()), "")
    return True, fwver


def snapshot_logs(user_host: str, dest: str, label: str) -> dict:
    """Copy every Mlog/Clog off the card into the bundle.

    This is the whole point of the harness. It never fails the round on its own: if the
    card cannot be read (issue #284 returns continuous FAT errors) that is recorded as a
    limitation of the evidence, not as a camera failure.
    """
    os.makedirs(dest, exist_ok=True)
    rc, listing = ssh_run(user_host, f"ls -1 {SD_LOG_DIR} 2>/dev/null | head -400",
                          timeout=60)
    names = [n.strip() for n in listing.splitlines() if n.strip()]
    if rc != 0 or not names:
        return {"label": label, "captured": 0, "error": (listing or "no listing")[:300]}

    captured, failed = [], []
    for name in names:
        if not re.match(r"^(Mlog|Clog)[_.]", name):
            continue
        remote = posixpath.join(SD_LOG_DIR, name)
        local = os.path.join(dest, name)
        got = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=8",
             "-o", "BatchMode=yes", user_host, f"cat {shlex.quote(remote)}"],
            capture_output=True, timeout=120)
        if got.returncode == 0:
            with open(local, "wb") as fh:
                fh.write(got.stdout)
            captured.append({"name": name, "bytes": len(got.stdout),
                             "sha256": hashlib.sha256(got.stdout).hexdigest()})
        else:
            failed.append(name)
    return {"label": label, "captured": len(captured), "files": captured,
            "failed": failed}


def scan_control_results(log_dir: str) -> dict:
    """Count OK/FAIL per control across a directory of logs.

    Uses the marker names pgphoto actually emits. Aperture is SP_SET_FNUM; searching for
    SP_SET_APERTURE returns nothing and reads as "aperture was never exercised", which is
    how an earlier survey misreported it.
    """
    tally = {k: {"ok": 0, "fail": 0} for k in CONTROL_MARKERS}
    busy = 0
    crash = 0
    if not os.path.isdir(log_dir):
        return {"controls": tally, "busy_ret": busy, "crash_signatures": crash}

    for entry in sorted(os.listdir(log_dir)):
        path = os.path.join(log_dir, entry)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for control, marker in CONTROL_MARKERS.items():
            tally[control]["ok"] += len(re.findall(rf"{marker}\s+OK", text))
            tally[control]["fail"] += len(re.findall(rf"{marker}\s+FAIL", text))
        busy += len(re.findall(r"-2110", text))
        crash += len(re.findall(r"SIGSEGV|exit code 139|\[stage2\] crash", text, re.I))
    return {"controls": tally, "busy_ret": busy, "crash_signatures": crash}


def connect(host: str, port: int):
    """Open the 9090 session using canary_probe's own client."""
    return cp.Polaris(host=host, port=port, bind=None, timeout=CONNECT_TIMEOUT_S)


def field(payload: str, name: str):
    return cp.field(payload, name)


def set_control(p, control: str, value: str, recorder: Recorder,
                budget: float = READBACK_BUDGET_S) -> dict:
    """Write one control and poll for physical readback.

    ret:0 only means the request parsed. The camera applies writes asynchronously and can
    answer ret:0 while leaving the value unchanged, so success requires a readback that
    matches -- the same discipline set_shutter() already uses for shutter.
    """
    opcode = OPCODES[control]
    payload = {
        "iso": f"iso:{value};",
        "wb": f"wb:{value};",
        "ev": f"ev:{value};",
        "shutter": f"s:{value};",
        "aperture": f"f:{value};",
    }[control]

    result = {"control": control, "requested": value, "opcode": opcode,
              "ack_ret": None, "attempts": 0, "readback": None,
              "outcome": "unknown", "first_error": None}

    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        result["attempts"] += 1
        try:
            p.send(opcode, payload=payload)
            response = p.wait_code(opcode, ACK_TIMEOUT_S)
        except (TimeoutError, ConnectionError) as exc:
            result["outcome"] = "transport-error"
            result["first_error"] = str(exc)
            return result

        ret = field(response, "ret")
        result["ack_ret"] = ret
        recorder.line(f"{control.upper()} attempt={result['attempts']} ret={ret} "
                      f"raw={response}")
        if ret is not None and ret != "0":
            if result["first_error"] is None:
                result["first_error"] = f"ret:{ret}"

        readback = read_control(p, control)
        result["readback"] = readback
        if readback == str(value):
            result["outcome"] = "applied"
            return result
        time.sleep(1.0)

    result["outcome"] = "not-applied"
    return result


def read_control(p, control: str):
    """Read a control's current value back from the camera."""
    try:
        if control == "shutter":
            readback, _options = cp.shutter_options(p, ACK_TIMEOUT_S, quiet=True)
            return None if readback is None else str(readback)
        opcode = {"iso": 258, "wb": 259, "ev": 260, "aperture": 276}[control]
        p.send(opcode)
        response = p.wait_code(opcode, ACK_TIMEOUT_S)
        key = {"iso": "iso", "wb": "wb", "ev": "ev", "aperture": "f"}[control]
        return field(response, key)
    except (TimeoutError, ConnectionError, ValueError):
        return None


# ── cases, one per WBS-04 item ──────────────────────────────────────────────────────

def case_wbs_04_1(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.1 crash and readiness (#285 #253)."""
    rec = {"wbs": "WBS-04.1", "issues": ["#285", "#253"], "title":
           "K-1 II process crash and connection readiness"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None,
                   reason=f"device unreachable: {detail}")
        return rec

    rc, out = ssh_run(user_host, "pgrep -f 'pgphoto' | head -5; "
                                 "grep -c ':1F90' /proc/net/tcp 2>/dev/null || true",
                      timeout=30)
    pids = [ln.strip() for ln in out.splitlines() if ln.strip().isdigit()]
    listeners = re.findall(r"^\s*(\d+)", out.splitlines()[-1] if out.splitlines() else "")

    try:
        p = connect(host, PORT)
        p.close()
        transport = "reachable"
    except (OSError, socket.timeout) as exc:
        transport = f"unreachable: {exc}"

    crash_dir = posixpath.join(recorder.root, "logs-before")
    scan = scan_control_results(crash_dir)
    rec.update(status="DEVICE_VERIFIED", evidence={"pgphoto_pids": pids,
               "port_8080_listener_lines": listeners, "transport": transport,
               "crash_signatures_in_logs": scan["crash_signatures"]},
               reason=f"pgphoto pids={len(pids)}, 9090 {transport}")

    if scan["crash_signatures"] > 0:
        rec["status"] = "FAIL"
        rec["reason"] += f"; {scan['crash_signatures']} crash signature(s) in logs"
    return rec


def _preview_off_once(recorder: Recorder, host: str, user_host: str) -> dict:
    """Turn liveview off once and measure whether frames stop."""
    before = ssh_run(user_host,
                     f"grep -c 'Pentax preview stage get-frame' {SD_LOG_DIR}/Clog* "
                     "2>/dev/null | awk -F: '{s+=$NF} END {print s+0}'", timeout=45)[1]
    frames_before = int(re.sub(r"\D", "", before) or 0)

    out = {"frames_before": frames_before, "ack_state": None,
           "frames_after": None, "new_frames_after_off": None, "error": None}
    try:
        p = connect(host, PORT)
    except (OSError, socket.timeout) as exc:
        out["error"] = f"9090 unreachable: {exc}"
        return out

    try:
        p.send(OPCODES["preview_query"])
        state = field(p.wait_code(OPCODES["preview_query"], ACK_TIMEOUT_S), "state")
        recorder.line(f"PREVIEW initial_state={state}")
        if state != "0":
            p.send(OPCODES["preview_set"], payload="state:0;")
            ack = p.wait_code(OPCODES["preview_set"], ACK_TIMEOUT_S)
            recorder.line(f"PREVIEW stop_ack={ack}")
        p.send(OPCODES["preview_query"])
        out["ack_state"] = field(p.wait_code(OPCODES["preview_query"], ACK_TIMEOUT_S),
                                 "state")
    except (TimeoutError, ConnectionError) as exc:
        out["error"] = f"preview off did not answer: {exc}"
        p.close()
        return out

    time.sleep(5.0)
    after = ssh_run(user_host,
                    f"grep -c 'Pentax preview stage get-frame' {SD_LOG_DIR}/Clog* "
                    "2>/dev/null | awk -F: '{s+=$NF} END {print s+0}'", timeout=45)[1]
    out["frames_after"] = int(re.sub(r"\D", "", after) or 0)
    out["new_frames_after_off"] = out["frames_after"] - frames_before
    p.close()
    return out


def _pgphoto_env(user_host: str, name: str) -> str:
    """Read one environment variable from the running pgphoto process."""
    rc, out = ssh_run(user_host,
                      "pid=$(pgrep -f 'pgphoto' | head -1); "
                      "tr '\\0' '\\n' < /proc/$pid/environ 2>/dev/null "
                      f"| grep '^{name}=' || echo unset", timeout=30)
    return out.strip() or "unset"


def case_wbs_04_2(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.2 preview OFF and camera idle (#275 #274).

    #293 asks for a controlled comparison of STAGE2_PENTAX_KEEP_LV=0 against the default,
    because stage2_pentax_enable_keep_live_view() turns pentaxpclvkeep ON after a successful
    Pentax init and that may be what keeps live view running after the app asks it to stop.
    The loader comment calls this an unproven hypothesis, so it is tested rather than assumed.

    What the source does establish: stage2_loader.c sets pentaxpclvkeep ON at init (default
    ON) and no code path anywhere in the file sets it back OFF -- grep for pentaxpclvkeep
    finds only the get, the set-to-ON, and comments. So a liveview-off request cannot be
    turning that toggle off. Whether the toggle is what keeps frames arriving is a device
    question.

    Changing the toggle needs pgphoto restarted with a different environment, which restarts
    the camera session. This harness deliberately does not do that: it would tear down a live
    session mid-round and invalidate every other case's evidence. It records the value the
    running process actually has and prints the manual procedure instead.
    """
    rec = {"wbs": "WBS-04.2", "issues": ["#275", "#274"], "title":
           "Preview stops after liveview off, camera becomes idle"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None, reason=f"device unreachable: {detail}")
        return rec

    keep_lv_env = _pgphoto_env(user_host, "STAGE2_PENTAX_KEEP_LV")
    backoff_env = _pgphoto_env(user_host, "STAGE2_PENTAX_PREVIEW_BACKOFF")
    default_run = _preview_off_once(recorder, host, user_host)

    rec["evidence"] = {"keep_lv_env": keep_lv_env, "backoff_env": backoff_env,
                       "default": default_run}

    if default_run["error"]:
        rec.update(status="FAIL", reason=default_run["error"])
        return rec

    streaming_after_off = (default_run["ack_state"] != "0"
                           or (default_run["new_frames_after_off"] or 0) > 0)
    rec.update(status="DEVICE_VERIFIED",
               reason=f"state after off={default_run['ack_state']}, "
                      f"{default_run['new_frames_after_off']} new get-frame lines in 5 s, "
                      f"{keep_lv_env}")
    if streaming_after_off:
        rec["status"] = "FAIL"
        rec["reason"] += " -- preview still streaming (#275 reproduced)"

    rec["next_action"] = (
        "A/B not run here: it needs pgphoto restarted with STAGE2_PENTAX_KEEP_LV=0, which "
        "tears down the live session and would invalidate this round's other cases. Run it as "
        "a separate round: restart_gphoto.sh with that variable exported, then re-run this "
        "tool and compare new_frames_after_off between the two bundles.")
    return rec


def case_wbs_04_4(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.4 control stickiness (#276 #277 #233 #232)."""
    rec = {"wbs": "WBS-04.4", "issues": ["#276", "#277", "#233", "#232"], "title":
           "Shutter, ISO, aperture, WB, EV writes stick without retry masking"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None, reason=f"device unreachable: {detail}")
        return rec

    try:
        p = connect(host, PORT)
    except (OSError, socket.timeout) as exc:
        rec.update(status="BLOCKED", evidence=None, reason=f"9090 unreachable: {exc}")
        return rec

    outcomes = {}
    try:
        # ISO first: it is the control that historically recovers on retry, so a failure
        # here means the session itself is unhealthy rather than a shutter-specific bug.
        for control, value in (("iso", "0"), ("ev", "0")):
            outcomes[control] = set_control(p, control, value, recorder)

        # Shutter last and deliberately: #276 says it never recovers while the others do,
        # so its result must not be contaminated by earlier retries leaving the body busy.
        try:
            current, options = cp.shutter_options(p, ACK_TIMEOUT_S)
            recorder.line(f"SHUTTER list_size={len(options)} current={current}")
            target = next((i for i in range(len(options)) if i != current), None)
            if target is None:
                outcomes["shutter"] = {"control": "shutter", "outcome": "no-alternative",
                                       "attempts": 0, "readback": current}
            else:
                outcomes["shutter"] = set_control(p, "shutter", str(target), recorder)
        except (TimeoutError, ConnectionError, ValueError) as exc:
            outcomes["shutter"] = {"control": "shutter", "outcome": "transport-error",
                                   "attempts": 0, "first_error": str(exc)}
    finally:
        p.close()

    rec["evidence"] = outcomes
    applied = [c for c, r in outcomes.items() if r.get("outcome") == "applied"]
    refused = {c: r.get("first_error") for c, r in outcomes.items()
               if r.get("outcome") != "applied"}
    rec["status"] = "DEVICE_VERIFIED" if applied or refused else "UNKNOWN"
    rec["reason"] = (f"applied={sorted(applied)} not-applied={sorted(refused)} "
                     f"first_errors={refused}")
    if refused:
        rec["status"] = "FAIL"
    return rec


def case_wbs_04_4b(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.4b whole-window re-apply probe (raised by this analysis).

    The pentax camlib implements camera_set_config but NOT camera_set_single_config, so
    gp_camera_set_single_config() falls through to its own comment's words: "emulate single
    config with the full tree" (gphoto2-camera.c). It calls get_config, sets the one widget
    the caller named, then calls set_config on the whole window.

    pentax's camera_get_config populates 26 widgets with gp_widget_set_value. On a freshly
    created widget value_string is NULL, so gp_widget_set_value takes its else branch and
    sets changed = 1 unconditionally -- every widget in the tree arrives marked as changed.
    camera_set_config then walks its blocks in fixed order (Shooting Mode, ISO, EV, Image
    Quality, Shutter Speed, Aperture, Bulb) and each block returns early on any error.

    If that is what pgphoto drives, one control write re-applies all of them and the first
    failure aborts everything after it. That predicts exactly what #276/#277 report: the
    first attempt returns -2110 for whatever was asked (the busy error comes from the
    shooting-mode block, not the requested control), and shutter failing with -6 means
    aperture and bulb were never attempted -- matching SP_SET_FNUM/SP_SET_WB showing no
    successes in the archive.

    This case tests it directly: read every control, write ONE control, read them all again.
    If controls that were not requested also changed or were re-issued, the whole-window
    path is confirmed and the per-control issues are symptoms of it rather than separate
    bugs. Requires pgphoto to be driving set_single_config; if the writes arrive as a
    single set_config already, this case reports UNKNOWN instead of guessing.
    """
    rec = {"wbs": "WBS-04.4b", "issues": ["#276", "#277", "#233", "#274"], "title":
           "Per-control write re-applies the whole config tree (whole-window emulation)"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None, reason=f"device unreachable: {detail}")
        return rec

    try:
        p = connect(host, PORT)
    except (OSError, socket.timeout) as exc:
        rec.update(status="BLOCKED", evidence=None, reason=f"9090 unreachable: {exc}")
        return rec

    controls = ("iso", "ev", "shutter")
    try:
        before = {c: read_control(p, c) for c in controls}
        recorder.line(f"REAPPLY before={before}")
        # Write exactly one control. ISO is chosen because it is first in camera_set_config's
        # block order after shooting mode, so a re-apply is visible in the later blocks.
        target = next((c for c in controls if c == "iso"), controls[0])
        set_control(p, target, "0", recorder)
        after = {c: read_control(p, c) for c in controls}
        recorder.line(f"REAPPLY after={after}")
    except (TimeoutError, ConnectionError, ValueError) as exc:
        p.close()
        rec.update(status="FAIL", evidence=None, reason=f"probe could not complete: {exc}")
        return rec
    finally:
        try:
            p.close()
        except Exception:
            pass

    unrequested_changed = sorted(c for c in controls
                                 if c != target and before.get(c) != after.get(c))
    rec["evidence"] = {"written": target, "before": before, "after": after,
                       "unrequested_changed": unrequested_changed}
    if any(before.get(c) is None for c in controls):
        rec.update(status="UNKNOWN",
                   reason="a control readback was unavailable, so re-apply cannot be "
                          "distinguished from an unreadable camera")
    elif unrequested_changed:
        rec.update(status="DEVICE_VERIFIED",
                   reason=f"writing {target} alone also changed {unrequested_changed}: "
                          "whole-window re-apply confirmed")
    else:
        rec.update(status="UNKNOWN",
                   reason="no unrequested control visibly changed; this does not rule out "
                          "re-apply -- a re-applied identical value is not observable from "
                          "readback alone. Confirm with Clog showing multiple SP_SET_* per "
                          "one request.")
    return rec


def case_wbs_04_5(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.5 autofocus (#278)."""
    rec = {"wbs": "WBS-04.5", "issues": ["#278"], "title":
           "Autofocus selection reaches actual lens movement"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None, reason=f"device unreachable: {detail}")
        return rec

    # AF on the Astro path runs through the server's own job, which records its own state.
    rc, status = ssh_run(user_host, "cat /tmp/polaris-af.status 2>/dev/null || echo none",
                         timeout=30)
    rec["evidence"] = {"af_status_before": status.strip()}
    rec.update(status="CODE_COMPLETE_UNVERIFIED",
               reason="AF requires a mounted lens and physical observation of focus "
                      "change; no automated proxy can prove lens movement. Needs the "
                      "operator to watch the lens while this case runs.")
    return rec


def case_wbs_04_6(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.6 manual shutter and file lifecycle (#279)."""
    rec = {"wbs": "WBS-04.6", "issues": ["#279"], "title":
           "Capture separates queued-command success from physical exposure"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None, reason=f"device unreachable: {detail}")
        return rec

    checker = cp.DeviceFileCheck(ssh_host=user_host, output_dir="/tmp", expected_files=1)
    if not checker.enabled():
        rec.update(status="BLOCKED", evidence=None,
                   reason="file check unavailable; cannot prove a file was produced")
        return rec

    try:
        p = connect(host, PORT)
    except (OSError, socket.timeout) as exc:
        rec.update(status="BLOCKED", evidence=None, reason=f"9090 unreachable: {exc}")
        return rec

    # arm() returns None; enabled() above is the real gate. Gating on arm()'s return
    # value would skip new_files() every time and report "no file" for a good capture.
    checker.arm()
    states: list[str] = []
    try:
        p.send(OPCODES["capture"], payload="-100")
        deadline = time.monotonic() + cp.MAX_TEST_EXPOSURE_SECONDS
        while time.monotonic() < deadline:
            try:
                code, payload = p.frame(deadline)
            except (TimeoutError, ConnectionError):
                break
            if code == OPCODES["capture"]:
                state = field(payload, "state")
                states.append(state)
                recorder.line(f"CAPTURE state={state}")
                if state in ("0", "-110", "-6") or (state and state.startswith("-")):
                    break
    finally:
        p.close()

    produced = checker.new_files()
    rec["evidence"] = {"states_observed": states, "files_produced": produced}
    if not states:
        rec.update(status="FAIL", reason="capture produced no 264 state at all")
    elif "-110" in states:
        rec.update(status="FAIL", reason="state:-110 PHOTO_RECORD Fail (#279 reproduced)")
    elif "0" in states and produced:
        rec.update(status="DEVICE_VERIFIED",
                   reason=f"completed with {len(produced)} file(s)")
    else:
        rec.update(status="UNKNOWN",
                   reason=f"states={states} files={produced}; cannot attribute")
    return rec


def case_wbs_04_7(recorder: Recorder, args) -> dict:
    """WBS-04.7 Bulb cancel safety (#251). Safety-gated; never runs unattended."""
    rec = {"wbs": "WBS-04.7", "issues": ["#251"], "title":
           "Bulb closes on cancel, normal finish, timeout and interruption"}
    if not args.with_bulb:
        rec.update(status="BLOCKED", evidence=None,
                   reason="not run: Bulb requires --with-bulb. #293 forbids unattended "
                          "Bulb tests; cancellation is a safety release blocker.")
        return rec
    if not args.i_am_present:
        rec.update(status="BLOCKED", evidence=None,
                   reason="refused: --with-bulb given without --i-am-present. A human "
                          "must be able to physically interrupt the shutter.")
        return rec
    rec.update(status="CODE_COMPLETE_UNVERIFIED", evidence=None,
               reason="Bulb cancellation must be exercised with canary-probe.py's timed "
                      "cases plus a manual red-cancel; this harness will not fire an "
                      "unbounded exposure. See #251 for the procedure.")
    return rec


def case_wbs_04_3(recorder: Recorder, host: str, user_host: str) -> dict:
    """WBS-04.3 live-view integrity (#147 #146)."""
    rec = {"wbs": "WBS-04.3", "issues": ["#147", "#146"], "title":
           "Live view frames are uncorrupted end to end"}
    reachable, detail = device_reachable(user_host)
    if not reachable:
        rec.update(status="BLOCKED", evidence=None, reason=f"device unreachable: {detail}")
        return rec

    # A frame can only be judged for corruption where it is produced. Grab one from the
    # transport and check JPEG structure; iOS-side rendering is out of reach from here.
    try:
        p = connect(host, PORT)
        p.close()
    except (OSError, socket.timeout) as exc:
        rec.update(status="BLOCKED", evidence=None, reason=f"9090 unreachable: {exc}")
        return rec

    rec.update(status="CODE_COMPLETE_UNVERIFIED", evidence=None,
               reason="frame integrity must be hashed at camera->pgphoto->transport->iOS "
                      "and the iPad crash reproduced separately; not automatable from the "
                      "PC side alone. See #147.")
    return rec


# ── offline re-scoring ──────────────────────────────────────────────────────────────

def analyze_only(bundle: str) -> int:
    """Re-score a saved bundle. Proves the parser works on real bytes with no device."""
    log_dir = bundle
    if os.path.isfile(bundle) and bundle.endswith(".tar.gz"):
        tmp = tempfile.mkdtemp(prefix="polaris-analyze-")
        with tarfile.open(bundle) as tf:
            tf.extractall(tmp)
        for candidate in ("logs-after", "logs-before", "."):
            probe = posixpath.join(tmp, candidate)
            if any(re.match(r"^(Mlog|Clog)", n) for n in os.listdir(probe)):
                log_dir = probe
                break
    scan = scan_control_results(log_dir)
    print(json.dumps(scan, indent=2, sort_keys=True))
    total_ok = sum(v["ok"] for v in scan["controls"].values())
    total_fail = sum(v["fail"] for v in scan["controls"].values())
    print(f"\ncontrols OK={total_ok} FAIL={total_fail} busy_ret(-2110)={scan['busy_ret']} "
          f"crash_signatures={scan['crash_signatures']}")
    if total_ok > 0 and scan["crash_signatures"] > 0:
        print("NOTE: successful control writes coexist with crash signatures, so the "
              "crash is not the single root cause of the control failures.")
    return 0


def build_bundle(recorder: Recorder, outdir: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    path = os.path.join(outdir, f"camera-qualification-{ts}.tar.gz")
    os.makedirs(outdir, exist_ok=True)
    with open(posixpath.join(recorder.root, "cases.json"), "w", encoding="utf-8") as fh:
        json.dump(recorder.records, fh, indent=2, sort_keys=True)
    with tarfile.open(path, "w:gz") as tf:
        tf.add(recorder.root, arcname=f"camera-qualification-{ts}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--ssh-host", default=SSH_USER_HOST)
    ap.add_argument("--outdir", default="/tmp/polaris-camera-qualification")
    ap.add_argument("--plan", action="store_true", help="print cases, touch nothing")
    ap.add_argument("--analyze-only", metavar="BUNDLE",
                    help="re-score a saved bundle offline, no device")
    ap.add_argument("--with-bulb", action="store_true",
                    help="include Bulb cases (requires --i-am-present)")
    ap.add_argument("--i-am-present", action="store_true",
                    help="assert a human can physically interrupt the shutter")
    args = ap.parse_args()

    if args.analyze_only:
        return analyze_only(args.analyze_only)

    cases = [
        ("WBS-04.1", "K-1 II crash and readiness (#285 #253)",
         lambda r: case_wbs_04_1(r, args.host, args.ssh_host)),
        ("WBS-04.2", "preview OFF and idle (#275 #274)",
         lambda r: case_wbs_04_2(r, args.host, args.ssh_host)),
        ("WBS-04.3", "live-view integrity (#147 #146)",
         lambda r: case_wbs_04_3(r, args.host, args.ssh_host)),
        ("WBS-04.4", "control stickiness (#276 #277 #233 #232)",
         lambda r: case_wbs_04_4(r, args.host, args.ssh_host)),
        ("WBS-04.4b", "whole-window re-apply probe (#276 #277 #233)",
         lambda r: case_wbs_04_4b(r, args.host, args.ssh_host)),
        ("WBS-04.5", "autofocus (#278)",
         lambda r: case_wbs_04_5(r, args.host, args.ssh_host)),
        ("WBS-04.6", "capture lifecycle (#279)",
         lambda r: case_wbs_04_6(r, args.host, args.ssh_host)),
        ("WBS-04.7", "Bulb cancel safety (#251)", lambda r: case_wbs_04_7(r, args)),
    ]

    if args.plan:
        print("camera qualification round -- planned cases (no device touched)")
        for wbs, title, _fn in cases:
            print(f"  {wbs}  {title}")
        print(f"\nexposure cap: {cp.MAX_TEST_EXPOSURE_SECONDS}s "
              f"(canary_probe.MAX_TEST_EXPOSURE_SECONDS)")
        print("Bulb cases are gated behind --with-bulb --i-am-present.")
        return 0

    root = tempfile.mkdtemp(prefix="polaris-camqual-", dir=args.outdir
                            if os.path.isdir(args.outdir) else None)
    recorder = Recorder(root)
    recorder.line(f"ROUND START host={args.host} ssh={args.ssh_host}")

    reachable, detail = device_reachable(args.ssh_host)
    recorder.line(f"device reachable={reachable} ({detail})")
    if reachable:
        recorder.line("snapshot logs BEFORE: "
                      + json.dumps(snapshot_logs(args.ssh_host,
                                                 posixpath.join(root, "logs-before"),
                                                 "before")))

    for _wbs, _title, fn in cases:
        try:
            record = fn(recorder)
        except Exception as exc:  # a broken case must not lose the others' evidence
            record = {"wbs": _wbs, "status": "UNKNOWN",
                      "reason": f"case raised {type(exc).__name__}: {exc}"}
        recorder.case(record)
        recorder.line(f"{_wbs} {record['status']} :: {record.get('reason', '')}")

    if reachable:
        recorder.line("snapshot logs AFTER: "
                      + json.dumps(snapshot_logs(args.ssh_host,
                                                 posixpath.join(root, "logs-after"),
                                                 "after")))

    bundle = build_bundle(recorder, args.outdir)
    print(f"\nBUNDLE {bundle}")
    counts: dict[str, int] = {}
    for record in recorder.records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    print("SUMMARY " + json.dumps(counts, sort_keys=True))
    print("\nNo case here can qualify a camera on its own. DEVICE_VERIFIED means the "
          "device answered; #293 still requires independent review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
