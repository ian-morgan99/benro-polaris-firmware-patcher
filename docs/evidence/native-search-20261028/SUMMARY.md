# Native independent-solver tile-search check

**Date:** 2026-10-28
**Scope:** host-only native C search front end over the real-Gaia regional
catalogue used by the paired solver check. This is integration evidence, not
Polaris or camera qualification.

## What changed

`polaris-solve-independent-search.c` now performs the tile selection and
bounded hint/corkscrew queue in C. It launches the native
`polaris-solve-independent` child without a shell, requires a readable tile
manifest, passes the focal/scale/match gates, compares successful attempts, and
returns the strongest candidate. The Python search wrapper remains a host
policy reference and is not part of the device path.

The production-shaped front-end settings are:

- 60 brightest records per tile;
- 0.15 relative scale tolerance;
- at least 12 unique catalogue matches;
- early return at 20 matches with RMS no greater than 1.5 px;
- a hard attempt budget, with 40 as the default for a hinted run.

## Real-Gaia smoke

Input was the 500-record ESA Gaia DR3 regional sample documented in
[`dual-solver-gaia-20261028/SUMMARY.md`](../dual-solver-gaia-20261028/SUMMARY.md),
partitioned into nine 10°×10° tiles. The same 4096×3072 rendered JPEG and
40-star extraction were used.

With no RA/Dec hint, the native front end reached the correct tile in five
bounded attempts and returned:

```json
{"solved":true,"ra_deg":84.50363698,"dec_deg":-2.69253795,
 "scale_arcsec_per_px":7.263815,"rotation_deg":17.044168,
 "matched_count":25,"rms_px":1.403887,
 "search_attempts":5,"search_mode":"all-sky-tile-centres"}
```

With the RA 84.5°, Dec -2.7° hint, it returned 25 matches and 0.912492 px
RMS in five attempted tile/position combinations. The host runs measured about
1.6 seconds wall time and 2.3 MB peak RSS for the five-attempt checks.

## Qualification boundary

This proves that the device-facing search executable can exercise the native C
solver over a versioned tile directory without Python. It does not prove a
complete all-sky Gaia package: only nine regional tiles were present, tile
ordering is a bounded search policy rather than a descriptor index, and the
result is still a rendered frame. ARM/GLIBC compatibility, SD-card resource
budget, real camera frames, and physical Polaris operation remain open gates.
