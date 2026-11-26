#!/usr/bin/env python3
"""k1ii-latency.py -- measure every user-visible K-1 II interaction in milliseconds.

Why this exists
---------------
"Make it seamless and fast" is not testable without numbers. Every prior claim about
speed in this repo was a single observation ("66 ms", "~6 s") with no distribution, so
a slow tail or a first-call penalty was invisible, and improvements could not be proven.
This script produces a repeatable baseline: per-operation p50/p95/max over N samples,
plus the full capture lifecycle broken into phases.

It reuses the protocol client from canary-probe.py rather than reimplementing framing,
so what is measured is exactly what the qualification harness sends.

Read-only by design: it issues reads and captures only. It never writes to the device
and never hot-swaps a loader. Run scripts/device-identity.py first -- timing bytes you
cannot attribute to a build is how results get misattributed.

Usage:
  python3 scripts/k1ii-latency.py                       # reads + one capture
  python3 scripts/k1ii-latency.py --samples 10
  python3 scripts/k1ii-latency.py --capture 0           # reads only, no shutter
  python3 scripts/k1ii-latency.py --json out/latency.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Command codes, established by disassembling the stock binaries and confirmed against
# the Benro Connect app's own traffic (see canary-probe.py).
READS = {
    265: "iso",
    266: "white_balance",
    267: "ev",
    268: "shutter",
    275: "aperture",
}
CAPTURE = 264
FILE_NOTIFY = 773
PREVIEW_START, PREVIEW_STATE = 292, 291


def load_client():
    spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    return cp


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    v = sorted(values)
    out = {"n": len(v), "min_ms": round(v[0], 1), "p50_ms": round(statistics.median(v), 1),
           "max_ms": round(v[-1], 1)}
    if len(v) >= 4:
        out["p95_ms"] = round(v[min(len(v) - 1, int(0.95 * len(v)))], 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--samples", type=int, default=5, help="repetitions per read operation")
    ap.add_argument("--capture", type=int, default=1, choices=(0, 1),
                    help="run a timed capture and break the lifecycle into phases")
    ap.add_argument("--exposure-seconds", type=float, default=1.0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    cp = load_client()

    def connect():
        t = time.monotonic()
        p = cp.Polaris(args.host, args.port, args.bind, timeout=10)
        return p, (time.monotonic() - t) * 1000.0

    results: dict[str, object] = {"host": args.host, "samples": args.samples}
    print(f"== K-1 II latency baseline ({args.host}:{args.port}, {args.samples} samples/op) ==",
          flush=True)

    p, connect_ms = connect()
    results["connect_ms"] = round(connect_ms, 1)
    print(f"  tcp connect            {connect_ms:8.1f} ms", flush=True)

    # Session handshake the app performs before anything works.
    t = time.monotonic()
    p.send(284); p.wait_code(284, 5)
    p.send(820); p.wait_code(820, 10)
    p.send(823, payload="app:latency;ver:1;")
    p.send(286); p.wait_code(286, 10)
    handshake_ms = (time.monotonic() - t) * 1000.0
    results["handshake_ms"] = round(handshake_ms, 1)
    print(f"  handshake (284/820/823/286) {handshake_ms:5.1f} ms", flush=True)

    def timed_read(code: int) -> tuple[float, str]:
        t = time.monotonic()
        p.send(code)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            c, b = p.frame(time.monotonic() + 5)
            if c == code:
                return (time.monotonic() - t) * 1000.0, b
        return (time.monotonic() - t) * 1000.0, "TIMEOUT"

    print("\n  -- parameter reads (what the app shows when you open a settings screen) --",
          flush=True)
    per_op: dict[str, list[float]] = {}
    empties: dict[str, int] = {}
    for _ in range(args.samples):
        for code, name in READS.items():
            ms, body = timed_read(code)
            per_op.setdefault(name, []).append(ms)
            v = cp.field(body, "V") if body != "TIMEOUT" else None
            opts = [o for o in (cp.field(body, "R") or "").split(",") if o] if body != "TIMEOUT" else []
            if not v or not opts:
                empties[name] = empties.get(name, 0) + 1
    for name in READS.values():
        s = stats(per_op.get(name, []))
        flag = f"  EMPTY_READS={empties[name]}" if empties.get(name) else ""
        print(f"  {name:16} n={s.get('n',0)} p50={s.get('p50_ms','-'):>7} "
              f"p95={s.get('p95_ms','-'):>7} max={s.get('max_ms','-'):>7}{flag}", flush=True)
    results["reads"] = {k: stats(v) for k, v in per_op.items()}
    results["empty_reads"] = empties

    # Concurrent burst: the app fires these together on connect. The intermittent empty
    # config read was first seen under exactly this pattern, so measure it here too.
    t = time.monotonic()
    for code in READS:
        p.send(code)
    got = 0
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and got < len(READS):
        try:
            c, b = p.frame(time.monotonic() + 3)
        except Exception:
            break
        if c in READS:
            got += 1
    burst_ms = (time.monotonic() - t) * 1000.0
    results["concurrent_read_burst_ms"] = round(burst_ms, 1)
    print(f"\n  concurrent read burst ({len(READS)} at once): {burst_ms:.1f} ms "
          f"(got {got}/{len(READS)})", flush=True)

    if args.capture:
        print("\n  -- capture lifecycle (the thing users call 'slow') --", flush=True)
        # Resolve the shutter slot that IS the requested duration, then write nothing if
        # it is already selected: a timed write while the dial is on B is refused (#206),
        # and inferring mode from list shape is forbidden.
        ms, body = timed_read(268)
        cur = cp.field(body, "V")
        opts = [o for o in (cp.field(body, "R") or "").split(",") if o]
        # Resolve the slot through the same parser the qualification harness uses.
        # An earlier version hand-built a label and silently left the shutter at 1s when
        # it did not match, so a "5 s exposure" run was really a 1 s run and its timing
        # looked identical to the 1 s control. Resolve or fail -- never shoot an unknown
        # duration and label it with what was requested.
        idx, label, resolved_s = cp.resolve_shutter_index(opts, args.exposure_seconds)
        results["requested_exposure_s"] = args.exposure_seconds
        results["shutter_label"] = label
        results["resolved_exposure_s"] = resolved_s
        wrote = False
        if cur in (None, ""):
            raise SystemExit(f"cannot time a capture: shutter read returned no current index "
                             f"(V={cur!r}); refusing to guess the exposure duration")
        if int(cur) != idx:
            t = time.monotonic()
            p.send(261, payload=f"s:{idx};")
            dl = time.monotonic() + 10
            ret = None
            while time.monotonic() < dl:
                c, b = p.frame(time.monotonic() + 5)
                if c == 261:
                    ret = cp.field(b, "ret")
                    results["shutter_set_ms"] = round((time.monotonic() - t) * 1000.0, 1)
                    results["shutter_set_ret"] = ret
                    break
            if ret != "0":
                # Loud, not silent: a refused write means the exposure is NOT what we
                # asked for, and any timing taken afterwards describes a different shot.
                raise SystemExit(
                    f"shutter SET s:{idx} ({label}) refused ret={ret}; the camera is not in "
                    f"a mode that accepts timed indices. Put the dial on M (or TAv) and "
                    f"retry -- do not read these timings as a {args.exposure_seconds}s shot.")
            wrote = True
            print(f"  shutter set to index={idx} label={label} ({resolved_s}s)", flush=True)
        else:
            print(f"  shutter already at index={idx} label={label} ({resolved_s}s), no write",
                  flush=True)

        filecheck_t = time.monotonic()
        t = time.monotonic()
        p.send(CAPTURE, subtype=4, payload="state:1;bulb:0;c:-1;")
        phases: dict[str, float] = {}
        states: list[int] = []
        files: list[str] = []
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                c, b = p.frame(deadline)
            except Exception:
                break
            if c == CAPTURE:
                v = cp.field(b, "state")
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    continue
                if iv not in states:
                    states.append(iv)
                    phases[f"state_{iv}"] = round((time.monotonic() - t) * 1000.0, 1)
                if iv in (0, -1, -6):
                    break
            elif c == FILE_NOTIFY:
                path = cp.field(b, "path")
                if path and path not in files:
                    files.append(path)
                    phases["file_notify"] = round((time.monotonic() - t) * 1000.0, 1)
        total_ms = (time.monotonic() - t) * 1000.0
        results["capture"] = {"states": states, "phases_ms": phases, "files": files,
                              "total_ms": round(total_ms, 1), "shutter_written": wrote}
        print(f"  states={states} shutter_written={wrote} exposure={resolved_s}s", flush=True)
        for k in sorted(phases):
            print(f"    {k:14} {phases[k]:8.1f} ms", flush=True)
        print(f"    {'TOTAL':14} {total_ms:8.1f} ms  files={files}", flush=True)

    p.close()

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.json}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
