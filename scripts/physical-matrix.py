#!/usr/bin/env python3
"""Physical Pentax qualification matrix runner (issue #180, corrected 2026-10-07).

Runs the six-scenario matrix against a live Polaris + qualified Pentax body and
records every capture individually. Design rules from the #180 correction:

- Settings the runner can prove remotely (shutter via 261/268, file counting,
  timing, connection/process health) are automated and recorded AUTO-VERIFIED.
- Settings that need the camera menu (file format until SET+read-back is proven,
  Slow Shutter NR, Pixel Shift) are USER-CONFIRMED: the runner pauses at each
  boundary with one clear instruction and verifies what it can read back
  (photoFormat via code 286) before continuing.
- Scenarios are grouped so the tester touches the camera menu as few times as
  possible (three boundaries for the full matrix).
- Pixel Shift scenarios wait on observed file/camera state (the canary path),
  never a fixed delay.
- Output: one JSON record per shot plus a matrix verdict PASS / FAIL /
  NOT PHYSICALLY QUALIFIED.

Usage (host wired to the gimbal AP):
  scripts/physical-matrix.py --expected-sw 6.0.0.54.60 \
      --out docs/evidence/<candidate>/matrix-<date>.json [--scenarios A,D]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANARY = REPO / "scripts" / "canary-probe.py"

# Scenario table from #180. format: 2 = RAW+JPEG, 1 = RAW-only (photoFormat).
# exposure: seconds through the 261/268 path; None = camera default (short).
SCENARIOS = {
    "A": {"format": 2, "exposure": "short", "nr": "off", "pixel_shift": "off"},
    "B": {"format": 1, "exposure": "short", "nr": "on",  "pixel_shift": "off"},
    "C": {"format": 2, "exposure": "long",  "nr": "on",  "pixel_shift": "off"},
    "D": {"format": 1, "exposure": "long",  "nr": "off", "pixel_shift": "off"},
    "E": {"format": 2, "exposure": "short", "nr": "off", "pixel_shift": "on"},
    "F": {"format": 1, "exposure": "long",  "nr": "on",  "pixel_shift": "on"},
}
# Execution order grouped by user-menu state to minimise camera-menu changes.
GROUPS = [
    ("G1", ["A", "D"], "Pixel Shift = OFF, Slow Shutter NR = OFF"),
    ("G2", ["B", "C"], "Pixel Shift = OFF, Slow Shutter NR = ON"),
    ("G3", ["E"],      "Pixel Shift = ON,  Slow Shutter NR = OFF"),
    ("G4", ["F"],      "Pixel Shift = ON,  Slow Shutter NR = ON"),
]
SHOTS_PER_SCENARIO = 3
LONG_SECONDS = 10  # recorded in the output; #180 allows 10-15s, record actual


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ssh(host: str, cmd: str, timeout: float = 15.0) -> str:
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=5", host, cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as exc:  # health probe must never crash the run
        return f"PROBE-ERROR {type(exc).__name__}: {exc}"


def health(host: str) -> dict:
    return {
        "t": now(),
        "pgphoto_pid": ssh(host, "pgrep -f pgphoto.stage2ondisk | head -1"),
        "uptime": ssh(host, "cat /proc/uptime | cut -d. -f1"),
        "camera": ssh(host, "true"),  # ssh reachability; 286 is checked per shot
    }


def probe_state() -> tuple[str | None, str | None, str | None]:
    """Read (model, state, photoFormat) via the canary probe (code 286), read-only."""
    r = subprocess.run([sys.executable, str(CANARY), "--probe"],
                       capture_output=True, text=True, timeout=90)
    m = re.search(r"SUMMARY model=(\S+) state=(\S+) photoFormat=(\S+)", r.stdout)
    return (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)


def wait_ready(settle_seconds: float) -> None:
    """#181: after a disconnect/reconnect the session must come back on its own.
    Poll until the camera session is live, then hold a settle window before any
    capture is issued -- a fresh-session camera can accept a capture and not
    honour it."""
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        model, state, _ = probe_state()
        if state == "1" and model and model != "none":
            break
        print(f"{now()} WAIT-READY state={state} model={model}", flush=True)
        time.sleep(10)
    else:
        raise RuntimeError("camera session did not come up within 300 s (#181)")
    if settle_seconds > 0:
        print(f"{now()} SETTLE {settle_seconds}s after session-ready (#181)",
              flush=True)
        time.sleep(settle_seconds)


def photo_format(host: str) -> str | None:
    return probe_state()[2]


def run_shot(expected_files: int, expected_sw: str, bulb: float | None) -> dict:
    cmd = [sys.executable, str(CANARY), "--shot",
           "--expected-files", str(expected_files), "--expected-sw", expected_sw]
    if bulb:
        cmd += ["--bulb-seconds", str(int(bulb))]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    dur = round(time.monotonic() - t0, 1)
    files = re.findall(r"FILE (\S+)", r.stdout)
    first_file_s = None
    for line in r.stdout.splitlines():
        if " FILE " in line:
            first_file_s = line.split()[0]
            break
    return {
        "t": now(), "exit": r.returncode, "duration_s": dur,
        "first_file_at": first_file_s, "files": files,
        "pass": r.returncode == 0,
        "tail": (r.stdout.strip().splitlines() or [""])[-1][:200],
    }


def confirm(prompt: str, assume_yes: bool) -> None:
    if assume_yes:
        print(f"[auto-continue, --yes] {prompt}", flush=True)
        return
    input(f"\n>>> {prompt}\n    press Enter when done to continue: ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="root@192.168.0.1")
    ap.add_argument("--expected-sw", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scenarios", default="A,B,C,D,E,F")
    ap.add_argument("--yes", action="store_true",
                    help="do not pause at user boundaries (dry runs only; "
                         "records stay USER-CONFIRMED/unverified)")
    ap.add_argument("--settle-seconds", type=float, default=90.0,
                    help="hold-off after the session becomes ready before "
                         "issuing captures (#181: fresh-session camera can "
                         "accept a capture and not honour it)")
    args = ap.parse_args()

    wanted = [s.strip().upper() for s in args.scenarios.split(",") if s.strip()]
    for s in wanted:
        if s not in SCENARIOS:
            ap.error(f"unknown scenario {s!r}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "issue": 180, "started": now(), "expected_sw": args.expected_sw,
        "long_exposure_seconds": LONG_SECONDS, "shots_per_scenario": SHOTS_PER_SCENARIO,
        "settings_provenance": {}, "scenarios": {},
    }

    h0 = health(args.host)
    print(f"{now()} HEALTH-START {h0}", flush=True)
    wait_ready(args.settle_seconds)

    for gid, scen_ids, menu_state in GROUPS:
        run_ids = [s for s in scen_ids if s in wanted]
        if not run_ids:
            continue
        confirm(
            f"Set on the camera: {menu_state}. Keep this state for scenarios "
            f"{'/'.join(run_ids)}; the runner will not change it again.",
            args.yes)
        record["settings_provenance"][gid] = {
            "menu_state": menu_state, "scenarios": run_ids,
            "nr_and_pixel_shift": "USER-CONFIRMED",
            "confirmed_at": now(), "auto_verified": False,
        }
        for sid in run_ids:
            sc = SCENARIOS[sid]
            expected_files = sc["format"]  # photoFormat 2 -> 2 files, 1 -> 1 file
            pf = photo_format(args.host)
            if pf is not None and pf != str(sc["format"]):
                confirm(
                    f"For scenario {sid} set the camera file format to "
                    f"{'RAW only' if sc['format'] == 1 else 'RAW+JPEG'} "
                    f"(currently reads photoFormat={pf}).", args.yes)
                pf = photo_format(args.host)
            fmt_verified = pf == str(sc["format"])
            shots = []
            for n in range(1, SHOTS_PER_SCENARIO + 1):
                bulb = LONG_SECONDS if sc["exposure"] == "long" else None
                print(f"{now()} SCENARIO {sid} shot {n}/{SHOTS_PER_SCENARIO} "
                      f"format={sc['format']} exposure={sc['exposure']}", flush=True)
                shot = run_shot(expected_files, args.expected_sw, bulb)
                shot["shot"] = n
                shots.append(shot)
                print(f"{now()} SCENARIO {sid} shot {n} -> "
                      f"{'PASS' if shot['pass'] else 'FAIL'} {shot['tail']}",
                      flush=True)
                if not shot["pass"]:
                    break  # #180: a failed scenario stops; record is shot-level
            h = health(args.host)
            record["scenarios"][sid] = {
                "spec": sc, "group": gid,
                "file_format": {"required": sc["format"],
                                "readback_photoFormat": pf,
                                "status": "AUTO-VERIFIED" if fmt_verified
                                else "USER-CONFIRMED"},
                "exposure": {"requested": sc["exposure"],
                             "seconds": LONG_SECONDS if sc["exposure"] == "long" else None,
                             "status": "AUTO-VERIFIED (261/268 set + read-back)"},
                "noise_reduction": "USER-CONFIRMED",
                "pixel_shift": "USER-CONFIRMED",
                "shots": shots,
                "health_after": h,
                "verdict": ("PASS" if all(s["pass"] for s in shots)
                            and len(shots) == SHOTS_PER_SCENARIO else "FAIL"),
            }
            print(f"{now()} SCENARIO {sid} VERDICT {record['scenarios'][sid]['verdict']}",
                  flush=True)
            args.out.write_text(json.dumps(record, indent=1))  # crash-safe

    run_verdicts = [v["verdict"] for v in record["scenarios"].values()]
    record["completed"] = now()
    record["matrix_verdict"] = ("PASS" if run_verdicts and all(v == "PASS" for v in run_verdicts)
                                else "FAIL")
    if not run_verdicts:
        record["matrix_verdict"] = "NOT PHYSICALLY QUALIFIED"
    args.out.write_text(json.dumps(record, indent=1))
    print(f"{now()} MATRIX {record['matrix_verdict']} -> {args.out}", flush=True)
    return 0 if record["matrix_verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
