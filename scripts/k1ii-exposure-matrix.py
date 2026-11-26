#!/usr/bin/env python3
"""k1ii-exposure-matrix.py -- does capture latency track the requested exposure?

Why this exists
---------------
Every timed capture in B mode took ~29.8 s and delivered a JPEG whose EXIF said
ExposureTime 20.0, because the body runs a 20-second Bulb timer there while command 268 still
reports the shutter as 00-01. That made latency look like a defect when it was the shutter being
open. To separate "exposure duration" from "overhead", this script measures several requested
durations in a mode that accepts timed indices (M or TAv) and reports overhead = total - exposure.

If overhead is roughly constant across durations, transmission/processing is fixed-cost -- which is
what the operator asserted about JPG and RAW -- and the only lever on latency is the exposure itself.

Reads are timed too: the first read of each parameter after a fresh session costs more than later
ones, and that cold penalty is what the app shows when you open a settings screen.

Usage:
  python3 scripts/k1ii-exposure-matrix.py --durations 1,5,10
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
TERMINAL = {0, -1, -6, -110, -112, -1005}
READS = {265: "iso", 266: "white_balance", 267: "ev", 268: "shutter", 275: "aperture"}


def stats_round(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "min_ms": round(min(vals), 1),
            "p50_ms": round(statistics.median(vals), 1), "max_ms": round(max(vals), 1)}


def load_client():
    spec = importlib.util.spec_from_file_location("cp", REPO / "scripts" / "canary-probe.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    return cp


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="192.168.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--bind", default="192.168.0.4")
    ap.add_argument("--durations", default="1,5,10", help="comma-separated exposure seconds")
    ap.add_argument("--repeats", type=int, default=2, help="shots per duration")
    ap.add_argument("--read-passes", type=int, default=3)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    cp = load_client()
    out: dict[str, object] = {}
    p = cp.Polaris(args.host, args.port, args.bind, timeout=10)
    p.send(284); p.wait_code(284, 5)
    p.send(820); p.wait_code(820, 10)
    p.send(823, payload="app:exposure-matrix;ver:1;")
    p.send(286); p.wait_code(286, 10)

    def read(code: int) -> tuple[float, str | None, list[str]]:
        t = time.monotonic()
        p.send(code)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                c, b = p.frame(time.monotonic() + 8)
            except Exception:
                break
            if c == code:
                ms = (time.monotonic() - t) * 1000.0
                opts = [o for o in (cp.field(b, "R") or "").split(",") if o]
                return ms, cp.field(b, "V"), opts
        return (time.monotonic() - t) * 1000.0, None, []

    print("== parameter reads (cold vs warm) ==", flush=True)
    cold: dict[str, float] = {}
    warm: dict[str, list[float]] = {}
    opts: list[str] = []
    cur: str | None = None
    for n in range(args.read_passes):
        parts = []
        for code, name in READS.items():
            ms, v, o = read(code)
            if code == 268 and o:
                opts, cur = o, v
            if n == 0:
                cold[name] = round(ms, 1)
            else:
                warm.setdefault(name, []).append(round(ms, 1))
            flag = "  EMPTY" if not o else ""
            parts.append(f"{name}={ms:.0f}ms(n={len(o)}){flag}")
        print(f"  pass {n + 1}: " + " | ".join(parts), flush=True)
    out["cold_read_ms"] = cold
    out["warm_read_ms"] = {k: stats_round(v) for k, v in warm.items()}
    if not opts:
        print("no shutter options; cannot resolve durations", file=sys.stderr)
        return 1

    print(f"\n== captures (shutter currently V={cur}, {len(opts)} options) ==", flush=True)
    rows = []
    for want in [float(x) for x in args.durations.split(",")]:
        idx, label, resolved = cp.resolve_shutter_index(opts, want)
        if abs(resolved - want) > 1e-6:
            print(f"  skip {want}s: no slot is that duration (nearest {label}={resolved}s)",
                  flush=True)
            continue
        # Always write the slot we want. Skipping the write when V already matches has been
        # wrong before: V can name a slot whose duration differs from what it implies.
        p.send(261, payload=f"s:{idx};")
        ret = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                c, b = p.frame(time.monotonic() + 8)
            except Exception:
                break
            if c == 261:
                ret = cp.field(b, "ret")
                break
        if ret != "0":
            print(f"  {label} ({resolved}s): SET refused ret={ret} -- is the dial on M or TAv?",
                  flush=True)
            continue
        for r in range(args.repeats):
            t = time.monotonic()
            ph: dict[str | int, float] = {}
            p.send(264, subtype=4, payload="state:1;bulb:0;c:-1;")
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                try:
                    c, b = p.frame(deadline)
                except Exception:
                    break
                if c == 264:
                    v = cp.field(b, "state")
                    try:
                        iv = int(v)
                    except (TypeError, ValueError):
                        continue
                    if iv not in ph:
                        ph[iv] = round((time.monotonic() - t) * 1000.0, 1)
                    if iv in TERMINAL:
                        break
                elif c == 773:
                    if "file" not in ph:
                        ph["file"] = round((time.monotonic() - t) * 1000.0, 1)
                        ph["path"] = cp.field(b, "path")
                        ph["size"] = cp.field(b, "size")
            total = round((time.monotonic() - t) * 1000.0, 1)
            states = sorted(k for k in ph if isinstance(k, int))
            # Success is "reached state 0 AND a file was notified". The first version asked
            # for sorted(states)[-1] == 0, but ascending sort puts 0 *first*, so every good
            # capture (states [0,1,4]) was reported FAIL and overhead came back None.
            ok = 0 in states and "file" in ph
            overhead = round(total - resolved * 1000.0, 1) if ok else None
            print(f"  {label} req={resolved}s shot {r + 1}: total={total}ms "
                  f"state4={ph.get(4)} file={ph.get('file')} overhead={overhead}ms "
                  f"states={states} {'OK' if ok else 'FAIL'}", flush=True)
            rows.append({"label": label, "requested_s": resolved, "shot": r + 1,
                         "total_ms": total, "state4_ms": ph.get(4), "file_ms": ph.get("file"),
                         "overhead_ms": overhead, "states": states, "ok": ok,
                         "path": ph.get("path"), "size": ph.get("size")})
            time.sleep(2)
    out["captures"] = rows
    good = [r["overhead_ms"] for r in rows if r.get("overhead_ms") is not None]
    if good:
        print(f"\n  overhead (total - exposure): n={len(good)} "
              f"min={min(good)}ms median={statistics.median(good)}ms max={max(good)}ms", flush=True)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"wrote {args.json}", flush=True)
    p.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
