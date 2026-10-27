#!/usr/bin/env python3
"""Wait for the Polaris to be usable: reachable, sshd up, camera attached.

Two failure modes this exists to handle, both observed on the bench:

  * The AP is up and pgphoto answers on 8080, but no ssh session succeeds. This
    script reports that as a distinct state rather than collapsing it into
    "unplugged". It deliberately does not name a cause: nothing here can observe
    which process holds port 22. (An earlier version blamed the Benro Connect app
    on no evidence, and in practice the message was produced by a broken ssh
    probe while sshd was healthy.)

  * The Polaris drops its own radio under sustained PTP traffic, and a camera
    body that has been idle reports state=-5 (no camera) or state=-2 (present but
    not ready). A qualification round started against either produces control
    failures that are really precondition failures -- #203's whole point is that
    those must not be recorded as results.

Exit codes:
  0  usable: sshd open and code 286 reports state=1 with a model
  1  timed out; the last observed state is printed
  2  usage/environment error
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

DEV_DEFAULT = "192.168.0.1"
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=6", "-o", "ServerAliveInterval=15"]


def run(cmd: list[str], timeout: float) -> tuple[int, str]:
    if not cmd or cmd[0].startswith("-"):
        # argv was built wrong (missing program name, or a slice that left a
        # dangling flag). subprocess would raise FileNotFoundError on "-o" and
        # the OSError handler below would turn that into rc=2 -- indistinguishable
        # from "the probe legitimately failed", which is exactly how sshd_open came
        # to report a healthy sshd as closed for months. Fail loudly instead.
        return 3, f"BUG: argv does not start with a program: {cmd[:3]!r}"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as exc:
        return 2, f"{type(exc).__name__}: {exc}"


def route_device(dev: str) -> str | None:
    """The interface a packet to `dev` would actually leave by.

    `ip route get` is preferred, but `ip` is not present in every environment
    (this shell runs in a sandbox without it), so fall back to reading the
    kernel routing table from /proc/net/route and doing the longest-prefix match
    ourselves. Both paths must agree on the answer or the check is worthless.
    """
    rc, out = run(["ip", "route", "get", dev], 10)
    if rc == 0 and out:
        head = out.split("via")[0]
        toks = head.split()
        if toks:
            return toks[-1]
    return route_device_from_proc(dev)


def route_device_from_proc(dev: str) -> str | None:
    """Longest-prefix match against /proc/net/route (no `ip` binary needed).

    Destination/Mask/Gateway in that file are printed as u32 in host byte order,
    so they are compared against inet_aton bytes unpacked the same way.
    Flags bit 0x1 marks a usable route.
    """
    import socket
    import struct
    try:
        raw = Path("/proc/net/route").read_text().splitlines()
    except OSError:
        return None
    try:
        target = struct.unpack("<I", socket.inet_aton(dev))[0]
    except OSError:
        return None
    best_if, best_len = None, -1
    for line in raw[1:]:
        f = line.split()
        if len(f) < 8:
            continue
        iface, dest, _gw, flags = f[0], f[1], f[2], f[3]
        try:
            if int(flags, 16) & 0x1 == 0:      # RTF_UP not set: unusable
                continue
            dest_i = int(dest, 16)
            mask_i = int(f[7], 16)
        except ValueError:
            continue
        if (target & mask_i) != dest_i:
            continue
        bits = bin(mask_i).count("1")
        if bits > best_len:
            best_if, best_len = iface, bits
    return best_if


def link_identity(dev: str, wifi_iface: str) -> tuple[bool, str]:
    """Prove `dev` is reached over the gimbal's own AP, not the home router.

    The Hitron router and the Polaris both answer 192.168.0.1, and the router
    answers it on port 80 with a GoAhead-Webs login page -- the same server
    banner the gimbal uses. Without this check a router probe is read as "the
    rig is up but sshd is closed", which is exactly the misdiagnosis this script
    exists to prevent. The route interface is the discriminator: the gimbal is
    only reachable via the Wi-Fi interface, never via the LAN cable.
    """
    rdev = route_device(dev)
    if rdev is None:
        return False, f"NO_ROUTE (no route to {dev})"
    if rdev != wifi_iface:
        return False, (f"WRONG_NETWORK -- {dev} is answered via {rdev}, not "
                       f"{wifi_iface}; that is the home router sharing the "
                       f"address, not the gimbal. Associate to the gimbal AP "
                       f"(polaris_*) on {wifi_iface}.")
    try:
        carrier = Path(f"/sys/class/net/{wifi_iface}/carrier").read_text().strip()
        operstate = Path(f"/sys/class/net/{wifi_iface}/operstate").read_text().strip()
    except OSError:
        return True, ""
    if carrier != "1" or operstate == "down":
        return False, (f"LINK_DOWN -- {wifi_iface} is {operstate} (carrier "
                       f"{carrier}); the gimbal AP is not associated")
    return True, ""


def ap_up(dev: str, port: int = 8080) -> bool:
    """Liveness by TCP connect to the control port, not ICMP.

    The first version used ping and immediately produced a false AP_DOWN: this
    shell runs inside the VS Code Flatpak sandbox, which drops ICMP but allows
    outbound TCP, so the rig looked dead while it was answering both ping and ssh
    from the host. Connecting to 8080 is the better probe anyway -- a live AP with
    pgphoto down is not usable, whereas ping only proves a radio is awake.
    """
    import socket
    try:
        with socket.create_connection((dev, port), timeout=6):
            return True
    except OSError:
        return False


def sshd_open(dev: str) -> bool:
    """True only if a real BatchMode ssh session succeeds.

    This previously sliced SSH_OPTS[:3], which is ["-o",
    "StrictHostKeyChecking=no", "-o"] -- a trailing -o with no argument. ssh
    exits 255 with 'no argument after keyword "root@<dev>"' for *any* host, so
    this function returned False unconditionally and the caller reported
    AP_UP_SSHD_CLOSED on a rig whose sshd was perfectly healthy. Verified: the
    device answers `ssh root@192.168.0.1 'cat /app/FwVer'` with
    FwVer:6.0.0.54.74 while this probe said sshd was closed.
    """
    rc, out = run(["ssh", *SSH_OPTS, f"root@{dev}", "echo up"], 12)
    return rc == 0 and "up" in out


def camera_state(dev: str, probe: str) -> tuple[str | None, str | None, str]:
    """Return (model, state, note) from the canary probe's SUMMARY line."""
    rc, out = run([sys.executable, probe, "--probe"], 90)
    for line in out.splitlines():
        if "SUMMARY model=" in line:
            fields = dict(item.split("=", 1) for item in line.split()
                          if "=" in item and not item.startswith("20"))
            return fields.get("model"), fields.get("state"), ""
    return None, None, (out.splitlines()[-1] if out else f"probe rc={rc}")


def self_test() -> int:
    """Assert each helper builds a runnable argv, without touching the network.

    This exists because sshd_open() passed an argv with no program name, so
    subprocess raised FileNotFoundError on "-o", run() swallowed it as rc=2, and
    the tool reported AP_UP_SSHD_CLOSED against a rig whose sshd was answering
    fine. A wrong argv is a programming error, not a device state, and must never
    be reported as one.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, timeout):
        calls.append(list(cmd))
        return 0, "up"

    global run
    real_run, run = run, fake_run
    try:
        sshd_open("192.168.0.1")
        camera_state("192.168.0.1", "scripts/canary-probe.py")
    finally:
        run = real_run

    failures = []
    for cmd in calls:
        if not cmd or cmd[0].startswith("-"):
            failures.append(f"argv has no program name: {cmd[:3]!r}")
    if not any(c and c[0] == "ssh" for c in calls):
        failures.append("sshd_open did not invoke ssh")
    if not any(c and c[0].endswith("python3") or (c and "canary-probe.py" in " ".join(c))
               for c in calls):
        failures.append("camera_state did not invoke the probe")
    # A dangling -o is the other half of the original bug.
    for cmd in calls:
        if "-o" in cmd and cmd.index("-o") == len(cmd) - 1:
            failures.append(f"dangling -o at end of argv: {cmd!r}")

    if failures:
        for f in failures:
            print(f"SELF-TEST FAIL: {f}")
        return 1
    print(f"SELF-TEST PASS ({len(calls)} argv(s) well-formed)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dev", default=DEV_DEFAULT)
    ap.add_argument("--probe", default="scripts/canary-probe.py")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="total seconds to wait for a usable rig")
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--self-test", action="store_true",
                    help="assert the helpers build valid argv and exit")
    ap.add_argument("--wifi-iface", default="wlp8s0",
                    help="interface the gimbal must be reachable through; a "
                         "route via any other interface means the address is "
                         "being answered by the home router")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    deadline = time.monotonic() + args.timeout
    last = "unknown"
    while time.monotonic() < deadline:
        ok_link, link_note = link_identity(args.dev, args.wifi_iface)
        if not ok_link:
            last = link_note
        elif not ap_up(args.dev):
            last = "AP_DOWN (no ping) -- is the Polaris powered and associated?"
        elif not sshd_open(args.dev):
            # State only. The old text asserted a cause ("the Benro Connect app
            # owns the session") that was never measured: nothing here can see
            # which process holds port 22, and the message was in fact printed by
            # a broken probe while sshd was working. Do not re-add a cause.
            last = ("AP_UP_SSHD_CLOSED -- the AP answers on 8080 but no BatchMode "
                    "ssh session succeeded; port 22 is not accepting us")
        else:
            model, state, note = camera_state(args.dev, args.probe)
            if state == "1" and model not in (None, "none"):
                print(f"READY model={model} state={state}")
                return 0
            last = f"SSH_OK camera model={model} state={state} {note}".strip()
        remaining = int(deadline - time.monotonic())
        print(f"[{time.strftime('%H:%M:%S')}] {last} (retrying, {remaining}s left)",
              flush=True)
        if remaining <= 0:
            break
        time.sleep(min(args.interval, max(remaining, 1)))

    print(f"NOT_READY {last}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
