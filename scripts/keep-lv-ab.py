#!/usr/bin/env python3
"""A/B whether keeping Pentax PC live view on contributes to issue #347.

Issue #347: a K-3 III fell off USB permanently during a goto slew, twice, in two
sessions. Re-analysis of the retained logs (see docs/issue-347-keep-lv-ab.md and
the comments on #347) narrowed it to one combination that has never survived:

    a SUSTAINED live view stream running while the mount is slewing

Session 34's fatal loss happened immediately after pgphoto served its 63rd
consecutive preview frame. Every earlier preview burst (1-16 frames with idle
gaps between) survived, and motor load on its own survived too -- 2868 motor
events over ~5.7 minutes with only bursty live view. The one removal that
recovered had no sustained stream at all.

STAGE2_PENTAX_KEEP_LV controls exactly this. It was defaulted ON by 08a8730 to
stop preview churn starving the Wi-Fi radio (#36/#55) and has never been
evaluated against USB stability; libgphoto2 itself calls the toggle a "research
harness". Issue #86 is direct precedent that live view teardown can take a Pentax
off USB -- on the K-1 II an empty frame reply was treated as fatal, the teardown
that followed took the camera off USB, and it was fixed by retrying instead.

This harness runs the same sequence under both settings and preserves the bytes.

Why it exists as a script rather than a checklist: every previous #347
post-mortem had to be reconstructed by hand from two log files, and dmesg had
already rolled past the event by the time anyone looked. Evidence capture is
built in, not documented.

Usage:
    keep-lv-ab.py --plan                     what it would run; touches nothing
    keep-lv-ab.py --host 192.168.0.1 --i-am-present --confirm-move
    keep-lv-ab.py --analyze-only BUNDLE      re-score saved bytes offline

Safety:
  * Moves the mount. Requires BOTH --i-am-present and --confirm-move, because a
    slew under load is exactly the condition that has previously killed the
    camera permanently and it must never be fired unattended or by a retry.
  * The slew is a bounded yaw nudge from --slew-deg (default 15), not a goto to
    an arbitrary sky coordinate, so it cannot drive into a hard stop chasing a
    target the harness invented.
  * Live view is always stopped on exit, including on error and Ctrl-C: leaving
    PC live view asserted is precisely the state that keeps a Pentax awake and
    wedged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Reuse the existing transport + ssh helpers instead of duplicating the 9090
# framing, following camera-qualification-round.py's precedent.
_spec = importlib.util.spec_from_file_location(
    "polaris_canary_probe", os.path.join(HERE, "canary-probe.py"))
cp = importlib.util.module_from_spec(_spec)
sys.modules["polaris_canary_probe"] = cp
_spec.loader.exec_module(cp)

SSH_USER_HOST = "root@192.168.0.1"
SD_LOG_DIR = "/app/sd/system/log"
HTTPD_PORT = 8080
MOUNT_PORT = 9090
RESTART = "/app/restart_gphoto"
# Written by the wrapper's allowlisted reader (pgphoto.wrapper.in). Read, not
# sourced: only STAGE2_PENTAX_KEEP_LV is honoured.
ENV_FILE = "/var/run/openpolaris-stage2.env"

ARMS = ("keep-on", "keep-off")
CAMERA_VENDORS = ("25fb",)          # Pentax / Ricoh
# Presence markers pgphoto/polestar_app actually emit. Verified against the
# retained session 34 logs: a present body is reported as
# `code[286],val[manufacturer:ricoh imaging company...]` -- NOT "pentax". The
# literal `25fb` does appear, but only 4 times in Clog and never in Mlog, and
# only inside the supervisor's own fingerprint lines, so it is far too sparse to
# score presence on. `manufacturer:none;model:none` is the ABSENT marker and must
# not match, so the pattern is explicit rather than a loose "manufacturer:"
# prefix -- scoring an absent body as present would silently turn a lost-camera
# run into a pass.
PRESENT_RE = re.compile(r"manufacturer:(ricoh|pentax)", re.I)
ABSENT_RE = re.compile(r"manufacturer:none", re.I)
# A healthy detach emits the interface uevents then the device; both fatal
# removals in the retained logs emitted two lines and stopped.
UEVENT_HEALTHY_MIN = 6


def stamp() -> str:
    return dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


def ssh_run(user_host: str, cmd: str, timeout: float = 60.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=8",
             "-o", "BatchMode=yes", user_host, cmd],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "ssh timed out"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def http_post(host: str, path: str, fields: dict, timeout: float = 15.0) -> tuple[int, str]:
    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(f"http://{host}:{HTTPD_PORT}{path}", data=data,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def snapshot_logs(user_host: str, dest: str, label: str) -> dict:
    """Copy Mlog/Clog plus dmesg into the bundle.

    dmesg is the whole point here: on this device the ring buffer holds only a
    few hundred lines, so the kernel's own reason for the removal had already
    rolled away in every previous post-mortem. It is pulled first, before the
    logs, because it is the volatile one.
    """
    os.makedirs(dest, exist_ok=True)
    out = {"label": label, "captured": 0}

    rc, dmesg = ssh_run(user_host, "dmesg 2>/dev/null | tail -400", timeout=60)
    with open(os.path.join(dest, "dmesg.txt"), "w") as fh:
        fh.write(dmesg)
    out["dmesg_rc"] = rc
    out["dmesg_usb_lines"] = len([l for l in dmesg.splitlines()
                                  if re.search(r"usb|xhci|hub", l, re.I)])

    rc, listing = ssh_run(user_host, f"ls -1 {SD_LOG_DIR} 2>/dev/null | head -400",
                          timeout=60)
    names = [n.strip() for n in listing.splitlines() if n.strip()]
    if rc != 0 or not names:
        out["error"] = (listing or "no listing")[:300]
        return out

    captured, failed = [], []
    for name in names:
        if not re.match(r"^(Mlog|Clog)[_.]", name):
            continue
        remote = posixpath.join(SD_LOG_DIR, name)
        got = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=8",
             "-o", "BatchMode=yes", user_host, f"cat {shlex.quote(remote)}"],
            capture_output=True, timeout=120)
        if got.returncode == 0:
            with open(os.path.join(dest, name), "wb") as fh:
                fh.write(got.stdout)
            captured.append({"name": name, "bytes": len(got.stdout),
                             "sha256": hashlib.sha256(got.stdout).hexdigest()})
        else:
            failed.append(name)
    out["captured"] = len(captured)
    out["files"] = captured
    if failed:
        out["failed"] = failed
    return out


def camera_present(user_host: str) -> bool:
    rc, out = ssh_run(user_host,
                      "for d in /sys/bus/usb/devices/*; do "
                      "[ -r $d/idVendor ] || continue; "
                      "v=$(tr A-F a-f < $d/idVendor); echo $v; done 2>/dev/null",
                      timeout=30)
    return any(v.strip() in CAMERA_VENDORS for v in out.splitlines())


def arm_keep_lv(user_host: str, value: str) -> tuple[bool, str]:
    """Write the allowlisted override and restart pgphoto so it takes effect.

    The loader reads STAGE2_PENTAX_KEEP_LV at gp_camera_init, so a restart is
    mandatory -- writing the file alone changes nothing in a running process.
    """
    rc, _ = ssh_run(user_host,
                    f"printf 'STAGE2_PENTAX_KEEP_LV=%s\\n' {shlex.quote(value)} "
                    f"> {ENV_FILE}", timeout=30)
    if rc != 0:
        return False, f"could not write {ENV_FILE}"
    rc, out = ssh_run(user_host, RESTART, timeout=120)
    if rc != 0:
        return False, f"{RESTART} exited {rc}: {out[:200]}"
    # Confirm from the wrapper's own log line rather than trusting the file.
    time.sleep(3)
    rc, seen = ssh_run(user_host,
                       f"grep -a 'keep-lv: override' {SD_LOG_DIR}/Clog* 2>/dev/null | tail -1",
                       timeout=30)
    return True, (seen.strip() or "no keep-lv override line found in Clog")


def clear_arm(user_host: str) -> None:
    ssh_run(user_host, f"rm -f {ENV_FILE}", timeout=30)


def stream_preview(p: cp.Polaris, seconds: float, stop_after: bool) -> int:
    """Start PC live view and keep consuming frames for `seconds`.

    Returns the number of frames actually pulled. This is the sustained-stream
    condition that session 34 was in when it died -- a continuous pull, not the
    bursty polling that has always survived.
    """
    p.send(291, 2, "state:1;")
    frames = 0
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            try:
                code, _payload = p.frame(deadline)
            except TimeoutError:
                break
            if code == 291:
                frames += 1
    finally:
        if stop_after:
            try:
                p.send(291, 2, "state:0;")
            except OSError:
                pass
    return frames


def slew(user_host: str, yaw_deg: float) -> tuple[int, str]:
    """Bounded yaw nudge through the confirmed opcode, then stop."""
    args = f"state:1;yaw:{yaw_deg:.3f};pitch:0;lat:0;lng:0;track:0;speed:800;"
    return http_post(user_host.split("@")[-1], "/api/link/send",
                     {"cmd": "519", "args": args, "confirm": "1"})


def stop_slew(user_host: str) -> None:
    http_post(user_host.split("@")[-1], "/api/link/send",
              {"cmd": "519", "args": "state:0;yaw:0;pitch:0;lat:0;lng:0;track:0;speed:0;",
               "confirm": "1"})


def analyse(log_dir: str) -> dict:
    """Score a bundle offline. Pure, so it can be unit-tested on synthetic logs."""
    res = {"frames": 0, "removals": [], "camera_seen": False,
           "truncated_removals": 0, "usb_evidence": 0}
    if not os.path.isdir(log_dir):
        res["error"] = f"no log dir: {log_dir}"
        return res
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    for name in sorted(os.listdir(log_dir)):
        if not re.match(r"^(Mlog|Clog)[_.]", name):
            continue
        text = ansi.sub("", open(os.path.join(log_dir, name),
                                 errors="replace").read())
        for line in text.splitlines():
            if "Pentax preview stage get-frame" in line:
                res["frames"] += 1
            if PRESENT_RE.search(line) and not ABSENT_RE.search(line):
                res["camera_seen"] = True
            if "usb-evidence:" in line:
                res["usb_evidence"] += 1
            m = re.search(r"\[(\d{2}:\d{2}:\d{2}):\d{3}.*remove@(\S*1-1\.2\S*)", line)
            if m:
                res["removals"].append({"t": m.group(1), "path": m.group(2)})
    # Group removal uevents into episodes by proximity, then flag any episode
    # that emitted fewer lines than a healthy teardown.
    episodes = []
    for r in res["removals"]:
        if episodes and r["t"] == episodes[-1]["t"]:
            episodes[-1]["n"] += 1
        else:
            episodes.append({"t": r["t"], "n": 1})
    for e in episodes:
        if e["n"] < UEVENT_HEALTHY_MIN:
            res["truncated_removals"] += 1
    res["removal_episodes"] = episodes
    return res


def verdict(results: list[dict]) -> str:
    """Interpret both arms. Deliberately refuses to over-claim on small n."""
    def survived(arm):
        rows = [r for r in results if r["arm"] == arm]
        if not rows:
            return None
        return all(r.get("camera_after") for r in rows)

    on, off = survived("keep-on"), survived("keep-off")
    if on is None or off is None:
        return "INCOMPLETE - one arm has no runs; do not draw a conclusion"
    if not on and off:
        return ("KEEP-LV IMPLICATED - keep-on lost the camera, keep-off survived. "
                "Implement idle live-view release per R2 in "
                "docs/issue-camera-idle-power-drain.md (session-ownership layer, "
                "NOT a process-global timer in stage2_loader.c -- #147 forbids it).")
    if on and off:
        return ("KEEP-LV NOT IMPLICATED - both arms survived. Stop chasing live "
                "view; focus on the truncated removal uevent stream.")
    if not on and not off:
        return ("BOTH FAIL - motor load during sustained streaming is fatal "
                "regardless of teardown policy. Look mount-side.")
    return "MIXED - keep-on survived but keep-off did not; unexpected, re-run"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--ssh-host", default=SSH_USER_HOST)
    ap.add_argument("--runs", type=int, default=3, help="repetitions per arm")
    ap.add_argument("--stream-secs", type=float, default=90.0)
    ap.add_argument("--slew-deg", type=float, default=15.0,
                    help="bounded yaw nudge; not an arbitrary sky target")
    ap.add_argument("--plan", action="store_true", help="print the plan, touch nothing")
    ap.add_argument("--analyze-only", metavar="BUNDLE")
    ap.add_argument("--i-am-present", action="store_true")
    ap.add_argument("--confirm-move", action="store_true")
    args = ap.parse_args()

    if args.analyze_only:
        log_dir = os.path.join(args.analyze_only, "logs")
        print(json.dumps(verdict(_load_results(args.analyze_only)), indent=2))
        print(json.dumps(analyse(log_dir), indent=2))
        return 0

    plan = [f"arm {a}: STAGE2_PENTAX_KEEP_LV={v}" for a, v in
            zip(ARMS, ("1", "0"))]
    if args.plan:
        print("PLAN (nothing executed):")
        for p in plan:
            print(f"  {p}")
        print(f"  per run: restart pgphoto -> confirm applied value -> start PC live "
              f"view -> stream frames {args.stream_secs}s -> bounded yaw slew "
              f"{args.slew_deg}deg while streaming -> stop both -> check camera present")
        print(f"  evidence per run: dmesg (first, it rolls), Mlog/Clog, "
              f"supervisor usb-evidence lines")
        print(f"  arms repeated {args.runs}x each")
        return 0

    if not (args.i_am_present and args.confirm_move):
        print("REFUSING: this moves the mount under load, which has previously "
              "killed the camera permanently.\nRe-run with both --i-am-present and "
              "--confirm-move.", file=sys.stderr)
        return 2

    if not camera_present(args.ssh_host):
        print("BLOCKED: no Pentax on USB before we start. Attach and power the "
              "body first; a run without a camera proves nothing.", file=sys.stderr)
        return 3

    bundle = os.path.join(HERE, "..", "docs", "evidence",
                          f"issue-347-keep-lv-ab-{dt.date.today():%Y%m%d}")
    os.makedirs(bundle, exist_ok=True)
    results: list[dict] = []
    try:
        for arm, value in zip(ARMS, ("1", "0")):
            ok, detail = arm_keep_lv(args.ssh_host, value)
            log(f"armed {arm} (STAGE2_PENTAX_KEEP_LV={value}): {detail}")
            if not ok:
                results.append({"arm": arm, "error": detail})
                continue
            for n in range(1, args.runs + 1):
                label = f"{arm}-run{n}"
                log(f"=== {label} ===")
                before = snapshot_logs(args.ssh_host,
                                       os.path.join(bundle, "logs"), label)
                p = cp.Polaris(args.host, MOUNT_PORT, None, 10.0)
                frames = 0
                try:
                    frames = stream_preview(p, args.stream_secs, stop_after=False)
                    rc, body = slew(args.host, args.slew_deg)
                    log(f"  slew rc={rc} {body[:120]}")
                    time.sleep(20)
                finally:
                    stop_slew(args.host)
                    try:
                        p.send(291, 2, "state:0;")
                    except OSError:
                        pass
                    p.close()
                time.sleep(5)
                present = camera_present(args.ssh_host)
                after = snapshot_logs(args.ssh_host,
                                      os.path.join(bundle, "logs"), label)
                results.append({"arm": arm, "run": n, "frames": frames,
                                "camera_after": present,
                                "logs_before": before.get("captured"),
                                "logs_after": after.get("captured")})
                log(f"  {label}: frames={frames} camera_present={present}")
                if not present:
                    log("  CAMERA LOST - stopping this arm; power-cycle the body "
                        "before continuing (a host reboot does not recover it)")
                    break
    finally:
        clear_arm(args.ssh_host)
        log("override cleared; pgphoto will use the shipped default on next start")

    with open(os.path.join(bundle, "results.json"), "w") as fh:
        json.dump({"results": results, "verdict": verdict(results)}, fh, indent=2)
    print(verdict(results))
    print(f"evidence bundle: {bundle}")
    return 0


def _load_results(bundle: str) -> list[dict]:
    path = os.path.join(bundle, "results.json")
    if not os.path.exists(path):
        return []
    return json.load(open(path)).get("results", [])


if __name__ == "__main__":
    sys.exit(main())
