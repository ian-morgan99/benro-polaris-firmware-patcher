# Native independent-solver tile-search check

**Date:** 2026-10-28
**Scope:** host-only native C search front end over the real-Gaia regional
catalogue used by the paired solver check. This is integration evidence, not
Polaris or camera qualification.

## What changed

`polaris-solve-independent-search.c` now performs the tile selection and
bounded hint/corkscrew queue in C. With a native triangle-ratio index it ranks
all-sky tile candidates before launching the native
`polaris-solve-independent` child without a shell. It requires a readable tile
manifest, passes the focal/scale/match gates, compares successful attempts, and
returns the strongest candidate. The Python search wrapper remains a host
policy reference and is not part of the device path.

The production-shaped front-end settings are:

- 60 brightest records per tile;
- 15 brightest records per tile in the triangle-ratio index;
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
`08c1d349798d0a7d5ef132df86ca38b59713d9ecf6b9882795a2a06fa7d10d51` (the
index bytes are unchanged after manifest metadata was added).

The package is a research artefact under `out/` and is not checked into the
source tree. The generated tile manifest carries the Gaia acknowledgement
notice; final distribution must retain that notice and the reproducible
manifest/checksum packaging step.

## All-sky-shaped Gaia smoke

Input was the 500-record ESA Gaia DR3 regional sample documented in
[`dual-solver-gaia-20261028/SUMMARY.md`](../dual-solver-gaia-20261028/SUMMARY.md),
partitioned into nine 10°×10° tiles. The same 4096×3072 rendered JPEG and
40-star extraction were used.

With no RA/Dec hint and a 648-tile, 482,106-record Gaia G<=10 catalogue, the
native triangle index ranked the correct tile first and returned:

```json
{"solved":true,"ra_deg":84.50363698,"dec_deg":-2.69253795,
 "scale_arcsec_per_px":7.263815,"rotation_deg":17.044168,
 "matched_count":25,"rms_px":1.403887,
 "search_attempts":1,"search_mode":"all-sky-triangle-index"}
```

The no-hint run returned 25 matches and 1.403887 px RMS in about 0.65 seconds
wall time and 4.5 MB peak RSS. With the RA 84.5°, Dec -2.7° hint, it returned
25 matches and 0.912492 px RMS in about 1.6 seconds for the five-attempt
regional check. The index is 2.3 MB and the tile set is 16 MB before package
compression.

## Qualification boundary

This proves that the device-facing search executable can exercise the native C
solver over an indexed all-sky-shaped tile set without Python. It does not yet
qualify the final Gaia package: the all-sky run used a rendered frame, the
triangle index needs wrong-solve and epoch/proper-motion testing, and the
catalogue/index provenance must be packaged atomically. ARM/GLIBC
compatibility, SD-card resource budget, real camera frames, and physical
Polaris operation remain open gates.
