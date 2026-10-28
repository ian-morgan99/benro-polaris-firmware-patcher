# Native solver tuning evidence — 2026-10-28

## Scope

This is a host-only regression comparison of the native independent solver
before and after the tuning pass. The paired-test generator now uses the exact
inverse gnomonic projection used by the solver. The independent catalogue is
still derived from the frame, so this is not an independent all-sky accuracy
qualification.

## Changes measured

- cached catalogue pair distances;
- default triangle-anchor cap of 15 bright observations;
- one-to-one observation/catalogue matching;
- all-inlier affine re-fit and RMS tie-break;
- cosine regional filtering in place of per-record `acos()`.

## Results

Thirty process launches per solver on the same host and same star list:

| Solver | Median | p95 | Matches | Fitted RMS |
|---|---:|---:|---:|---:|
| Previous native C | 39.5 ms | 41.8 ms | 19 | 0.000 px |
| Tuned native C | 35.0 ms | 37.2 ms | 19 | 0.000 px |
| Astrometry.net | 21.6 ms | 23.1 ms | 19 | not exposed by front end |

The tuned native result was 11.5% faster than the previous native build in this
corrected run, while remaining about 13 ms slower than Astrometry.net. The
native scale was 7.251497 arcsec/px against the generated 7.251497 arcsec/px;
the apparent 0.1% error in the earlier report came from the test catalogue
generator's projection approximation. These numbers should not be generalized
from one synthetic scene.

## Build status

- Host build: PASS.
- Existing Python/tool tests: 7 PASS.
- Direct ARM compilation: binary has the expected ARM soft-float ABI, but the
  current cross sysroot emits a GLIBC_2.34 dependency and therefore fails the
  repository's Polaris GLIBC_2.24 ceiling. This is a toolchain qualification
  blocker, not a solver algorithm result.

## Next accuracy work

1. Replace the scene-derived catalogue with a real Gaia regional tile.
2. Run repeated clean/noisy/partial/false-candidate fields.
3. Compare centre, scale, roll, false-solve rate, runtime and RSS distributions.
4. Only then tune the anchor count, residual threshold and scale tolerance for
   the actual Polaris ARM workload.
