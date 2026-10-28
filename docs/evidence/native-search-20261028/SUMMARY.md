# Native independent-solver tile-search check

**Date:** 2026-10-28
**Scope:** host-only native C search front end over a 648-tile Gaia DR3
package and five rendered scenes. This is integration evidence, not Polaris or
camera qualification.

## What changed

`polaris-solve-independent-search.c` now performs the tile selection and
bounded hint/corkscrew queue in C. With a native triangle-ratio index it ranks
all-sky tile candidates before launching the native
`polaris-solve-independent` child without a shell. It requires a readable tile
manifest, passes the focal/scale/match gates, compares successful attempts, and
returns the strongest candidate. The Python search wrapper remains a host
policy reference and is not part of the device path.

The production-shaped front-end settings are:

- 120 brightest records per tile in the matcher, with 10 observed triangle
  anchors;
- 15 brightest records per tile in the triangle-ratio index;
- 0.1% ratio bins with exact-bin lookup;
- 0.15 relative scale tolerance;
- at least 12 unique catalogue matches;
- early return at 20 matches with RMS no greater than 1.5 px;
- a hard attempt budget, with 40 as the default for a hinted run.

## All-sky-shaped Gaia package smoke

The ESA Gaia DR3 TAP query used for the package was:

```sql
SELECT source_id,ra,dec,phot_g_mean_mag
FROM gaiadr3.gaia_source
WHERE phot_g_mean_mag IS NOT NULL AND phot_g_mean_mag <= 10
```

It returned 482,106 records. The downloaded CSV SHA-256 is
`4205621ab59e287d98920799f2f75c30f729fe5794e55a73253ab3b6d3136af5`; the
tile manifest SHA-256 is
`35fc8382cd33073f1decca5592db58038de2f87f5ba515992a4ed318c2d34fb9`.
The 648 10°×10° tiles occupy about 16 MB, and the 294,840-record native
triangle index is 2.3 MB with SHA-256
`b432e9d0ee7af86b8a5f412cf10f1f149f9b62942d38df9a22973de239b41601`.
The tile-manifest SHA-256 is
`35fc8382cd33073f1decca5592db58038de2f87f5ba515992a4ed318c2d34fb9`.
The index manifest records ratio scale 1000 and the same source-manifest
checksum.

The package is a research artefact under `out/` and is not checked into the
source tree. The generated tile manifest carries the Gaia acknowledgement
notice; final distribution must retain that notice and the reproducible
manifest/checksum packaging step.

## Indexed Gaia solve corpus

The regional input was the 500-record ESA Gaia DR3 sample documented in
[`dual-solver-gaia-20261028/SUMMARY.md`](../dual-solver-gaia-20261028/SUMMARY.md),
partitioned into nine 10°×10° tiles. Four additional scenes were rendered
directly from the downloaded 648-tile Gaia package, at RA/Dec/roll
(5,-5,11), (155,15,29), (255,35,47), and (305,-35,83).

With no RA/Dec hint and a 648-tile, 482,106-record Gaia G<=10 catalogue, the
native triangle index selected the correct tile within the first five
candidates for every scene. The regional frame returned:

```json
{"solved":true,"ra_deg":84.50185836,"dec_deg":-2.69347882,
 "scale_arcsec_per_px":7.261666,"rotation_deg":17.048751,
 "matched_count":28,"rms_px":1.678303,
 "search_attempts":5,"search_mode":"all-sky-triangle-index"}
```

The no-hint run returned 28 matches and 1.678303 px RMS in 13.07 seconds for
the five-attempt run, with 4.8 MB peak RSS. The four additional real-Gaia
rendered scenes also solved without a hint:

| scene target (RA, Dec, roll) | matches | RMS px | attempts |
|---|---:|---:|---:|
| (5, -5, 11) | 23 | 1.544 | 5 |
| (155, 15, 29) | 12 | 1.065 | 5 |
| (255, 35, 47) | 17 | 1.231 | 5 |
| (305, -35, 83) | 15 | 1.078 | 5 |

The index is 2.3 MB and the tile set is 16 MB before package compression.
Observed ratios above the 16-bit on-disk range are discarded rather than
folded into the saturated key; this corrected a false candidate flood during
the native implementation check.

Negative contract checks on the same host build returned `search_exhausted`
for a 150 mm focal-length error, an empty star list, and a deliberately wrong
RA/Dec hint. Removing that wrong hint and rerunning the indexed all-sky search
returned the regional solve, which is the fallback now wired into
`polaris-align.sh`.

## Qualification boundary

This proves that the device-facing search executable can exercise the native C
solver over an indexed all-sky-shaped tile set without Python, and that the
real downloaded Gaia tile set can solve a small multi-position rendered corpus.
It does not yet qualify the final Gaia package: the scenes are rendered rather
than camera frames, the index needs wrong-solve and epoch/proper-motion testing,
and the catalogue/index provenance must be packaged atomically. ARM/GLIBC
compatibility, SD-card resource budget, real camera frames, and physical
Polaris operation remain open gates.
