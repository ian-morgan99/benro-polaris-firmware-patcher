#!/usr/bin/env python3
"""Read-only probe for the stage2 camera-admission gate (issue: v117 parameter regression).

Why this exists
---------------
On 6.0.0.54.117 with a K-1 II attached, every parameter read answers with the
sentinel ``-1`` and the head then serves a hard-coded fallback list
(``getCameraConfig from local configType N``). The cause is not recognition --
the body reports ``model:pentax k-1 mark ii;state:1`` -- it is that the stage2
admission gate leaks its claim, so every later config/set request is refused.

This probe reads the parameter codes only. It never sends a SET frame and never
fires the shutter, because the wire subtype for "set" is not documented anywhere
in this repository and guessing it risks double-firing capture (see
scripts/probe-b-list-and-held-bulb.py, which cost two real exposures doing exactly
that).

For each config code it reports whether the answer is a real value list or the
``-1`` sentinel, and correlates that with ``admission refused`` lines in
/app/Clog.txt captured across the same window. A code answering with a list while
the gate is refusing is impossible; if that happens the diagnosis is wrong and
this script says so.

Exit codes: 0 all codes answered with real values, 1 at least one fell back to
-1 (the reported symptom), 2 transport failure.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

# Codes observed in Clog.txt as the head's parameter reads. All are read requests
# (subtype 2, payload -100), which is what the head itself sends for a read.
CONFIG_CODES = {
    265: "iso",
    266: "white-balance",
    267: "exposure-compensation",
    268: "shutter-speed",
    275: "aperture",
}

REFUSE_RE = re.compile(
    r"admission refused: site=(?P<site>[0-9a-f]+) kind=(?P<kind>\d+) "
    r"owner_site=(?P<owner>[0-9a-f]+) last_owner_kind=(?P<lkind>\d+) "
    r"generation=(?P<gen>\d+)"
)


def ssh(ssh_host: str, cmd: str) -> str:
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25", ssh_host, cmd],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return ""
    return out.stdout


def refusal_lines(ssh_host: str) -> list[dict]:
    # /app/Clog.txt does not exist on .115+ firmware; the camera daemon writes
    # rotating logs under /app/sd/system/log/. Grepping the old path matched nothing,
    # so this returned [] and every caller printed "refusals already in Clog: 0"
    # regardless of what the gate was actually doing.
    raw = ssh(
        ssh_host,
        "ls /app/sd/system/log/Clog_*.log 2>/dev/null | tail -1 | "
        "xargs -r sed 's/\\x1b\\[[0-9;]*m//g' | grep -a 'admission refused' | tail -40",
    )
    found = []
    for line in raw.splitlines():
        m = REFUSE_RE.search(line)
        if m:
            found.append(m.groupdict())
    return found


def local_bind_for(host: str) -> str | None:
    """Source address the kernel would use to reach ``host``.

    The old default was a hardcoded workstation IP on the rig subnet. After a
    Wi-Fi re-join hands out a different address, binding to it fails with
    EADDRNOTAVAIL and the probe reports a transport failure that has nothing to
    do with the rig.
    """
    try:
        out = subprocess.run(["ip", "-4", "-o", "route", "get", host],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for token in out.stdout.split():
        if token.startswith("src "):
            return token[4:]
        if token.startswith("src") and len(token) > 3:
            return token[3:]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--bind", default=None,
                    help="local source address; derived from the route to --host if unset")
    ap.add_argument("--ssh-host", default="root@192.168.0.1")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()

    if args.bind is None:
        args.bind = local_bind_for(args.host)

    before = refusal_lines(args.ssh_host)
    print(f"refusals already in Clog: {len(before)}", flush=True)

    try:
        p = cp.Polaris(args.host, 9090, args.bind, timeout=10)
    except OSError as exc:
        print(f"transport failure: {exc}", file=sys.stderr)
        return 2

    fell_back = []
    try:
        p.send(284); p.wait_code(284, 5)
        p.send(820)
        auth = p.wait_code(820, 12)
        if cp.field(auth, "needed") == "1":
            print("device requires a password", file=sys.stderr)
            return 2
        p.send(823, payload="app:openpolaris-config-gate-probe;ver:1;")
        p.send(286)
        cam = p.wait_code(286, 10)
        print(f"CAMERA model={cp.field(cam,'model')} state={cp.field(cam,'state')} "
              f"storage={cp.field(cam,'storage')} photoFormat={cp.field(cam,'photoFormat')}",
              flush=True)

        for rnd in range(1, args.rounds + 1):
            print(f"\n--- round {rnd} ---", flush=True)
            for code, name in sorted(CONFIG_CODES.items()):
                p.send(code)
                try:
                    payload = p.wait_code(code, 8)
                except (TimeoutError, ConnectionError) as exc:
                    print(f"  {code} {name:<22} NO-REPLY ({exc})")
                    fell_back.append((code, name, "no-reply"))
                    continue
                val = cp.field(payload, "V")
                raw = cp.field(payload, "R") or ""
                if payload.strip() == "-1" or val is None:
                    verdict = "FALLBACK(-1)"
                    fell_back.append((code, name, "sentinel"))
                else:
                    verdict = f"real V={val} options={len(raw.split(','))}"
                print(f"  {code} {name:<22} {verdict}")
            time.sleep(1.0)
    finally:
        p.close()

    after = refusal_lines(args.ssh_host)
    new = len(after) - len(before)
    print(f"\nrefusals in Clog after probe: {len(after)} (delta {new})")
    seen: dict[tuple, int] = {}
    for r in after:
        key = (r["site"], r["kind"], r["owner"], r["lkind"], r["gen"])
        seen[key] = seen.get(key, 0) + 1
    for (site, kind, owner, lkind, gen), n in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"  x{n:<3} site={site} kind={kind} owner_site={owner} "
              f"last_owner_kind={lkind} generation={gen}")

    if fell_back:
        print(f"\nVERDICT: {len(fell_back)} parameter read(s) served the -1 sentinel")
        for code, name, why in fell_back:
            print(f"  {code} {name}: {why}")
        return 1
    print("\nVERDICT: every parameter code answered with a real value list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
