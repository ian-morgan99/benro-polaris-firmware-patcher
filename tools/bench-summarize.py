#!/usr/bin/env python3
"""#342: turn bench-capture-to-result.sh JSONL into median/p95 and a ranking.

Reads the JSONL the device tool emits (optionally several files, warm and cold)
and prints per-stage median/p95 plus a bottleneck-ranked recommendation. Pure
stdlib so it runs anywhere the corpus is stored.
"""
import argparse
import json
import statistics
import sys

STAGES = [
    ("extract_ms", "polaris-extract (decode + star find)"),
    ("quad_search_ms", "solver quad search"),
    ("index_load_ms", "index open/read"),
    ("star_read_ms", "star list parse"),
]


def pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    metas, runs = [], []
    for fn in args.files:
        with open(fn) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("record") == "meta":
                    metas.append(rec)
                elif rec.get("record") == "run":
                    runs.append(rec)

    if not runs:
        print("no run records found", file=sys.stderr)
        return 1

    if metas:
        m = metas[0]
        print(f"machine : {m.get('cpu')} x{m.get('cores')}, "
              f"{m.get('mem_total_kb', 0) // 1024} MB, load {m.get('load1')}")
        print(f"binaries: polaris-solve {m.get('polaris_solve_md5')} "
              f"(--timings={'yes' if m.get('timings_supported') else 'no'})")
        print(f"indexes : {m.get('indexes')} files, "
              f"{(m.get('index_bytes') or 0) / 1048576:.1f} MB")
        print(f"image   : {m.get('image')} ({m.get('image_bytes')} B, md5 {m.get('image_md5')})")

    for cold in (0, 1):
        sel = [r for r in runs if int(r.get("cold_cache", 0)) == cold]
        if not sel:
            continue
        label = "COLD cache" if cold else "warm cache"
        solved = sum(1 for r in sel if r.get("solved"))
        print(f"\n== {label}: {len(sel)} runs, {solved} solved ==")
        tot = [r.get("total_ms", 0) for r in sel]
        print(f"  total capture->result : median {pct(tot,50):.0f} ms  "
              f"p95 {pct(tot,95):.0f} ms")
        parts = []
        for key, label2 in STAGES:
            vals = [r[key] for r in sel if key in r]
            if not vals:
                continue
            med = statistics.median(vals)
            parts.append((med, label2, pct(vals, 50), pct(vals, 95)))
        denom = pct(tot, 50) or 1
        for med, label2, m50, p95 in sorted(parts, reverse=True):
            print(f"    {label2:<38} median {m50:7.1f} ms  p95 {p95:7.1f} ms  "
                  f"{100*med/denom:4.1f}% of total")
        rss = [r["peak_rss_kb"] for r in sel if "peak_rss_kb" in r]
        if rss:
            print(f"  peak RSS              : median {statistics.median(rss):.0f} KB")

    print("\n== bottleneck ranking ==")
    warm = [r for r in runs if int(r.get("cold_cache", 0)) == 0] or runs
    tot_med = statistics.median([r.get("total_ms", 0) for r in warm]) or 1
    ranked = []
    for key, label2 in STAGES:
        vals = [r[key] for r in warm if key in r]
        if vals:
            ranked.append((statistics.median(vals), label2))
    ranked.sort(reverse=True)
    for i, (med, label2) in enumerate(ranked, 1):
        print(f"  {i}. {label2}: {med:.0f} ms ({100*med/tot_med:.0f}% of median total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
