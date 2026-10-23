#!/usr/bin/env python3
"""Wait for the Polaris to be usable: reachable, sshd up, camera attached.

Two failure modes this exists to handle, both observed on the bench:

  * The Benro Connect app holds the only Wi-Fi/SSH session. When it closes, port
    22 stops answering while the AP still answers ping -- so a plain `ssh` probe
    reports "Connection refused" and looks like an unplugged rig. Reconnecting
    after the app is closed restores it. This script distinguishes the three
    states (AP down / AP up but sshd closed / sshd open) instead of collapsing
    them into one boolean.

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

DEV_DEFAULT = "192.168.0.1"
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=6", "-o", "ServerAliveInterval=15"]


def run(cmd: list[str], timeout: float) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as exc:
        return 2, f"{type(exc).__name__}: {exc}"


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
    rc, out = run([*SSH_OPTS[:3], f"root@{dev}", "echo up"], 12)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dev", default=DEV_DEFAULT)
    ap.add_argument("--probe", default="scripts/canary-probe.py")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="total seconds to wait for a usable rig")
    ap.add_argument("--interval", type=float, default=15.0)
    args = ap.parse_args(argv)

    deadline = time.monotonic() + args.timeout
    last = "unknown"
    while time.monotonic() < deadline:
        if not ap_up(args.dev):
            last = "AP_DOWN (no ping) -- is the Polaris powered and associated?"
        elif not sshd_open(args.dev):
            last = ("AP_UP_SSHD_CLOSED -- the Benro Connect app owns the session; "
                    "close it (or reconnect) to restore port 22")
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
