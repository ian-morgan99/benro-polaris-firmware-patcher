#!/usr/bin/env python3
"""k1ii-liveview-check.py -- does live view actually deliver frames on this build?

Why this exists
---------------
The qualification harness counts frames by grepping for 'Pentax preview stage get-frame'. That
string does not exist in the deployed loader, so using it reports 0 fps whether or not frames are
flowing -- a false negative that would look like a live-view regression. The marker this build
actually emits is '[stage2] K-1 II preview ret=%d elapsed_ms=%lld next_interval_s=%d', so count
that instead and print the raw lines, because the ret= value is what tells you whether frames are
arriving or the loader is in backoff.

Also records the control-socket traffic while preview is running: no JPEG frames arrive on 9090,
so the frame path is elsewhere and this script says so rather than guessing.

Usage:
  python3 scripts/k1ii-liveview-check.py --seconds 30
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARKER = "[stage2] K-1 II preview ret="
# The loader writes to the SD-rotated log, not /app/Clog.txt: pgphoto's stdout/stderr both point at
# /app/Clog.txt, but that file is truncated/rotated independently and in practice held zero
# '[stage2]' lines while Clog_NNNNNN.log on the card held 161. Counting the wrong file reports 0
# frames whether or not live view works -- the same false negative as grepping a marker string this
# build never emits.
LOG_GLOB = "/app/sd/system/log/Clog_* /app/Clog.txt"


def load_client():
    spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    return cp


def ssh(user_host: str, cmd: str, timeout: int = 45) -> str:
    return subprocess.run(["ssh", "-o", "BatchMode=yes", user_host, cmd],
                          capture_output=True, text=True, timeout=timeout).stdout


def count(user_host: str, marker: str) -> int:
    out = ssh(user_host,
              f"grep -ahc -- {shlex.quote(marker)} {LOG_GLOB} 2>/dev/null "
              "| awk '{s+=$1} END {print s+0}'")
    return int(re.sub(r"\D", "", out) or 0)


def samples(user_host: str, marker: str, n: int = 5) -> list[str]:
    out = ssh(user_host,
              f"grep -ah -- {shlex.quote(marker)} {LOG_GLOB} 2>/dev/null | tail -{n}")
    return [re.sub(r"\x1b\[[0-9;]*m", "", ln)[:140] for ln in out.splitlines()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--ssh", default="root@192.168.0.1")
    ap.add_argument("--seconds", type=float, default=30.0)
    args = ap.parse_args()

    cp = load_client()
    p = cp.Polaris(args.host, args.port, args.bind, timeout=10)
    p.send(284); p.wait_code(284, 5)
    p.send(820); p.wait_code(820, 10)
    p.send(823, payload="app:liveview-check;ver:1;")
    p.send(286); p.wait_code(286, 10)

    def preview_state(retries: int = 3) -> str | None:
        """Ask code 292 for the preview state, tolerating silence.

        292 does not always answer inside the window; the first version let that propagate as a
        TimeoutError and the script died before measuring anything.
        """
        for _ in range(retries):
            try:
                p.send(292)
                return cp.field(p.wait_code(292, 8), "state")
            except (TimeoutError, ConnectionError):
                continue
        return None

    # Start from a known-off state so the count window is honest.
    state = preview_state()
    if state != "0":
        try:
            p.send(291, payload="state:0;")
            p.wait_code(291, 8)
        except (TimeoutError, ConnectionError):
            pass
    print(f"preview off state={preview_state()}", flush=True)

    base = count(args.ssh, MARKER)
    any_stage2 = int(re.sub(r"\D", "", ssh(
        args.ssh,
        f"grep -ahc -- '[stage2]' {LOG_GLOB} 2>/dev/null | awk '{{s+=$1}} END {{print s+0}}'")
        or "0") or 0)
    print(f"marker {MARKER!r} baseline count={base}; any [stage2] lines={any_stage2}", flush=True)
    if base == 0 and not samples(args.ssh, MARKER):
        print("  marker absent -- this build never emits it, so frame rate cannot be attributed "
              "to it; report the ret= line or pick a different probe", flush=True)

    try:
        p.send(291, payload="state:1;")
        ack = p.wait_code(291, 15)
    except (TimeoutError, ConnectionError) as exc:
        print(f"start request did not answer: {exc}", flush=True)
        p.close()
        return 1
    print(f"start ack={ack}", flush=True)

    time.sleep(3)
    a = count(args.ssh, MARKER)
    t0 = time.monotonic()
    # Watch the control socket too: if frames were pushed here we would see large payloads.
    big: list[tuple[int, int]] = []
    deadline = t0 + args.seconds
    while time.monotonic() < deadline:
        try:
            c, b = p.frame(deadline)
        except Exception:
            break
        if len(b) > 512:
            big.append((c, len(b)))
    el = time.monotonic() - t0
    b_after = count(args.ssh, MARKER)
    calls = b_after - a
    print(f"\npreview calls in {el:.1f}s: {calls}  -> {calls / el:.2f}/s", flush=True)
    print(f"control-socket payloads >512B during that window: {len(big)} {big[:5]}", flush=True)
    for ln in samples(args.ssh, MARKER):
        print(f"  {ln}", flush=True)

    try:
        p.send(291, payload="state:0;")
        p.wait_code(291, 8)
    except (TimeoutError, ConnectionError):
        pass
    time.sleep(5)
    print(f"after stop: +{count(args.ssh, MARKER) - b_after} calls in 5s (expect ~0)", flush=True)
    p.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
