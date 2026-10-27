#!/usr/bin/env python3
"""Record the attached body's shutter-speed list shape (issue #217).

Why this exists
---------------
`.76` gates Bulb-list synthesis to the K-3 III, because the 13 published
second-counts were read from that body's own populated list. `.74` synthesised for
every model. So if a K-1 II (or KP/K70/Monochrome) ever reports an *empty* shutter
list, `.76` hands back the empty list -- which is exactly the condition #241 says
crashes Benro Connect.

Which of the two risks is real depends on a fact we have never recorded: no shutter
descriptor from any non-K-3-III body has ever been captured. This script captures it,
so the question can be closed with data instead of speculation.

What it records
---------------
  * model and USB ids as the gimbal sees them (code 286 + lsusb)
  * `gphoto2 --get-config shutterspeed` output, i.e. how many choices the widget
    ended up with -- zero choices means the body published an empty list and nothing
    was synthesised for it
  * whether libgphoto2's synthesis path fired, read from the device log

Exit codes
----------
  0  recorded (a camera is attached; verdict printed)
  1  no camera attached -- nothing recorded, retry after attaching one
  2  usage/environment error
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys

DEV_DEFAULT = "192.168.0.1"
# Same library path pgphoto loads (install-manifest.json), not the older
# /app/lib/libgphoto2/2.5.27.1 copy that also exists on the device.
CAMLIBS = "/app/lib/stage2/libgphoto2/2.5.34"
IOLIBS = "/app/lib/stage2/libgphoto2_port/0.12.2"
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15"]


def stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list[str], timeout: float) -> tuple[int, str]:
    if not cmd or cmd[0].startswith("-"):
        # A missing program name makes subprocess raise FileNotFoundError on the
        # first flag; swallowing that as a generic failure is what made
        # wait-for-rig.py report a healthy sshd as closed. Fail loudly instead.
        return 3, f"BUG: argv does not start with a program: {cmd[:3]!r}"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as exc:
        return 2, f"{type(exc).__name__}: {exc}"


def ssh(dev: str, remote: str, timeout: float = 60.0) -> tuple[int, str]:
    # "ssh" must be argv[0]. Writing [*SSH_OPTS, ...] starts the argv with "-o",
    # which subprocess tries to *execute*; run() now rejects that instead of
    # reporting it as a device failure (the bug class behind wait-for-rig.py's
    # false AP_UP_SSHD_CLOSED).
    return run(["ssh", *SSH_OPTS, f"root@{dev}", remote], timeout)


def camera_identity(dev: str) -> dict[str, str]:
    rc, out = ssh(dev, "lsusb 2>/dev/null | grep -i 25fb; "
                       "cat /app/FwVer 2>/dev/null")
    info = {"fwver": "", "usb": ""}
    for line in out.splitlines():
        if "FwVer" in line:
            info["fwver"] = line.strip()
        elif "25fb" in line:
            info["usb"] = line.strip()
    return info


def shutter_widget(dev: str) -> tuple[int, str]:
    """gphoto2's own view of the shutter-speed control."""
    env = f"CAMLIBS={CAMLIBS} IOLIBS={IOLIBS}"
    cmd = f"{env} /app/bin/gphoto2 --get-config shutterspeed 2>&1"
    return ssh(dev, cmd, timeout=120)


def synthesis_fired(dev: str) -> tuple[bool | None, str]:
    """Did libgphoto2 populate an empty list for this body?

    Reads the device log for the marker the synthesis path emits. Returns
    (None, note) when the log is unreadable -- absence of the marker is only
    evidence if the log was actually readable.
    """
    rc, out = ssh(dev, "tail -n 400 /app/sd/Mlog.txt 2>/dev/null; "
                       "tail -n 400 /tmp/polaris-identify.txt 2>/dev/null")
    if rc != 0 or not out.strip():
        return None, "device log unreadable; cannot confirm synthesis"
    hit = re.search(r"[^\n]*no JPEG\); added[^\n]*", out)
    if hit:
        return True, hit.group(0).strip()[:160]
    return False, "synthesis marker absent from the log tail"


def self_test() -> int:
    """Assert every helper builds a runnable argv, without touching the network."""
    calls: list[list[str]] = []

    def fake_run(cmd, timeout):
        calls.append(list(cmd))
        return 0, "FwVer:6.0.0.54.76;date:2026.10.27;\nBus 001 Device 003: ID 25fb:0183"

    global run
    real_run, run = run, fake_run
    try:
        camera_identity("192.168.0.1")
        shutter_widget("192.168.0.1")
        synthesis_fired("192.168.0.1")
    finally:
        run = real_run

    failures = [f"argv has no program name: {c[:3]!r}" for c in calls
                if not c or c[0].startswith("-")]
    if not all(c and c[0] == "ssh" for c in calls):
        failures.append("a helper did not invoke ssh")
    if len(calls) != 3:
        failures.append(f"expected 3 argv(s), got {len(calls)}")
    for f in failures:
        print(f"SELF-TEST FAIL: {f}")
    if failures:
        return 1
    print(f"SELF-TEST PASS ({len(calls)} argv(s) well-formed)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true",
                    help="assert the helpers build valid argv and exit")
    ap.add_argument("--dev", default=DEV_DEFAULT)
    ap.add_argument("--out", default="", help="write the record here as well")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    ident = camera_identity(args.dev)
    if not ident["usb"]:
        print(f"{stamp()} NO_CAMERA -- no Pentax (25fb) on the gimbal's USB. "
              f"Attach a body (PTP mode, not mass-storage) and re-run.", flush=True)
        return 1

    lines = [f"# shutter-list record, {stamp()}", "",
             f"fwver: {ident['fwver']}",
             f"usb:   {ident['usb']}", ""]

    rc, widget = shutter_widget(args.dev)
    choices = len(re.findall(r"^\s*\d+:\s", widget, flags=re.MULTILINE))
    lines += [f"## gphoto2 --get-config shutterspeed (rc={rc})", "",
              "```", widget.rstrip(), "```", "",
              f"**choices: {choices}**", ""]

    fired, note = synthesis_fired(args.dev)
    lines.append(f"synthesis fired: {fired} ({note})")
    lines.append("")

    if choices == 0:
        lines.append("## VERDICT: EMPTY LIST for this body")
        lines.append("")
        lines.append("The widget has no choices. If this is not a K-3 III, `.76`'s "
                     "model gate withheld synthesis and left the list empty -- the "
                     "#241 crash condition. Extend `pentax_shutter_list_may_synthesise_bulb()` "
                     "with this body's own published second-counts.")
        verdict = "EMPTY"
    else:
        lines.append("## VERDICT: list is populated")
        lines.append("")
        lines.append("This body publishes its own values, so the model gate is "
                     "harmless for it and no synthesis is needed.")
        verdict = "POPULATED"

    report = "\n".join(lines) + "\n"
    print(report, flush=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"wrote {args.out}", flush=True)

    print(f"SHUTTER_LIST verdict={verdict} choices={choices} "
          f"synthesis={fired} usb={ident['usb'][:40]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
