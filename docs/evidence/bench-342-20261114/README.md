# #342 — capture-to-result baseline on real Polaris hardware

Captured 2026-11-14. Grade A: run on the head against the deployed indexes with the
real shipped `polaris-extract`, and an ARM build of `polaris-solve` carrying the new
`--timings` instrumentation (`d5f9a78`).

Nothing deployed was touched. The instrumented solver ran from `/tmp` via a symlinked
`ASTRO` dir; artifacts live under gitignored `out/`.

## How to reproduce

    scp tools/bench-capture-to-result.sh <arm-polaris-solve> root@192.168.0.1:/tmp/
    ssh root@192.168.0.1 'mkdir -p /tmp/bastro && ln -sf /tmp/polaris-solve /tmp/bastro/ && \
      ln -sf /app/astro/polaris-extract /tmp/bastro/ && \
      ASTRO=/tmp/bastro RUNS=5 sh /tmp/bench-capture-to-result.sh' > warm.jsonl
    ssh root@192.168.0.1 'COLD=1 ASTRO=/tmp/bastro RUNS=5 sh /tmp/bench-capture-to-result.sh' > cold.jsonl
    python3 tools/bench-summarize.py warm.jsonl cold.jsonl

## Result

| stage | warm median | warm p95 | cold median | cold p95 | share (warm) |
|---|---|---|---|---|---|
| `polaris-extract` ds=1, 200 stars | 1800 ms | 1826 ms | 1850 ms | 1860 ms | **47.4%** |
| solver quad search | 1606 ms | 1690 ms | 1846 ms | 1891 ms | 42.3% |
| index open/read | 348 ms | 357 ms | 456 ms | 465 ms | 9.2% |
| star list parse | 2.4 ms | 2.7 ms | 3.9 ms | 4.0 ms | 0.1% |
| **total capture→result** | **3800 ms** | **3890 ms** | **4230 ms** | **4264 ms** | |

10/10 runs solved. Peak RSS ~11.6 MB warm, ~11.4 MB cold. Machine: ARMv7 rev 5, 2 cores,
1514 MB, load ~1.3. Indexes: 10 files, 44.1 MB at `/app/sd/astrometry`. Image md5
`d3790127717eb21faac8fe70a67f6b5c`, 155,048 B, 1920x1280, no EXIF. Solved on index-4117,
logodds 87.8, nmatch 12.

## Bottleneck ranking and what it means

1. **`polaris-extract` — 47%.** Previously unmeasured entirely: `polaris-solve` only ever
   timed `solver_run()`, so nearly half the wait was invisible. This is the first target.
2. **Quad search — 42%.** The other half; tunable via `--depth`, star count, quad bounds.
3. **Index load — 9%.** Real but bounded. Cold cache costs ~108 ms more than warm, so SD
   read speed is not the constraint. #343's pruning cannot recover more than this slice.
4. Star parse — negligible.

Cold vs warm total differs by only ~430 ms (~11%), so page-cache state is a minor factor;
the cost is compute, not I/O.

## Scope note — what this does NOT cover

`#342` asks for a **versioned multi-image corpus** (K-1 II, K-3 III, wide/telephoto, the
11 mm / 450 mm case, plus negative cases) with independently established truth. This
directory contains one real image, the #341 upload, whose WCS is self-consistent but not
externally verified. The corpus and independent truth remain open work; do not treat this
baseline as corpus-wide.

## After the extraction fix (`b820b25`) — `device-after-*.jsonl`

Re-measured with the same tool, same image, same indexes. The meta records prove which
binary ran: `polaris_extract_md5` is `1224d8b1…` in the before files and `0007e8c0…`
(the hoisted build) in the after files.

| stage | warm before | warm after | cold before | cold after |
|---|---|---|---|---|
| `polaris-extract` | 1800 ms | **1230 ms** | 1850 ms | **1260 ms** |
| solver quad search | 1606 ms | 1615 ms | 1846 ms | 1836 ms |
| index open/read | 348 ms | 350 ms | 456 ms | 471 ms |
| star list parse | 2.4 ms | 2.5 ms | 3.9 ms | 3.9 ms |
| **total capture→result** | **3800 ms** | **3250 ms** | **4230 ms** | **3640 ms** |

10/10 runs still solved, same index-4117, same logodds 87.8, peak RSS unchanged (~11.6 MB).
The quad-search and index-load figures are flat within noise, which is the expected result:
the change touches only extraction, so anything that did not move confirms the measurement
is not just global drift.

**Revised ranking.** Quad search is now #1 at ~50% (was 42%), extraction #2 at ~38% (was
47%). #344's parameter benchmarking (`--depth`, star count, quad bounds) is the next target;
index load remains capped near 11%.

**Correction.** The WBS entry for `b820b25` says total moves to "~3.14 s warm". That was
arithmetic on the extraction delta, not a measurement. The measured warm total is **3.25 s**
(3800 → 3250 ms). The difference is that `total_ms` includes process start-up and the star
file round-trip, which the per-stage figures do not.
