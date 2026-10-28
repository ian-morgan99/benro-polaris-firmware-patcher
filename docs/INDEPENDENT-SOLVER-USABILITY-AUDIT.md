# Independent solver usability audit

Status: host research prototype with passing paired synthetic and real-Gaia
regional-frame runs. Not device-qualified and not safe to select through
`SOLVER_BIN` as a production default.

## What works

- Deterministic star-list contract and JSON result/failure contract.
- Gaia-style catalogue reduction and `POLCAT01` binary format.
- Per-tile manifests and SHA-256 verification.
- Gaia-backed host sky renderer.
- Hint/corkscrew search policy and bounded subprocess attempts.
- Camera-model sensor profiles and EXIF focal-length precedence in the
  existing Astrometry alignment path.
- Thirteen deterministic tests pass.

## Native-C tuning pass

The first native-C implementation has now had a bounded tuning pass. It still
uses the same catalogue format and command-line contract, but:

- catalogue pair distances are cached once instead of recomputed for every
  observed/catalogue triangle;
- only the brightest 15 observations are used as triangle anchors by default,
  while all accepted observations remain available for verification;
- duplicate observations can no longer count against the same catalogue star;
- accepted candidates are re-fitted using all unique inliers, then scored by
  match count and RMS residual rather than match count alone; and
- the catalogue-region test uses a cosine threshold instead of `acos()` for
  every catalogue record.

The paired-test generator was also corrected to invert the exact gnomonic
projection used by the solver. Its earlier degree/cos(dec) approximation
introduced an artificial scale error of about 0.1%; that was a test-fixture
error, not a solver result. On the corrected paired frame, 30-process medians
were approximately 35.0 ms for the tuned native solver versus 39.5 ms for the
previous native build, while Astrometry.net measured approximately 21.6 ms.
Both native runs retained 19 matches. The corrected native scale was
7.251497 arcsec/px against the 7.251497 arcsec/px generated scale (displayed
error below 0.000001%). This is a zero-noise, scene-derived catalogue check,
not evidence of production accuracy.

Separate perturbation tests on the corrected synthetic star list produced
median absolute scale errors of 0.0011%, 0.0056% and 0.0111% for 0.1, 0.5 and
1.0 pixel centroid noise respectively. Real Gaia fields and camera frames are
still required before treating those figures as representative.

The tuning is therefore accepted as a host performance/robustness improvement,
not as a reason to change the production default. A real Gaia catalogue and a
multi-frame error distribution are still required.

## Blocking limitations

1. The independent solver and sky renderer now have native C host/ARM build
   paths, and the runtime selector supplies the regional catalogue arguments.
   The paired harness has run successfully on one host frame.
2. The native solver still requires a regional catalogue and does not perform a true
   all-sky blind solve. The corkscrew wrapper is a host experiment, not the
   device solver.
3. Candidate search is bounded brute force, not an indexed descriptor lookup;
   the real Gaia regional render now solves in roughly 3.8 seconds on the host
   after selecting the brightest regional records, but remains too expensive
   and memory-unbounded for an all-sky device catalogue.
4. The Gaia data currently used is a 500-star regional prototype, not an
   all-sky production catalogue. The run also exposed and fixed a real false
   candidate caused by selecting source-ID order rather than bright stars;
   see [the evidence summary](evidence/dual-solver-gaia-20261028/SUMMARY.md).
5. The native independent renderer has no camera distortion,
   vignetting, saturation, or colour/noise calibration.
6. The first paired run uses a synthetic catalogue derived from the known test
   scene. It is plumbing/matching evidence, not catalogue-independence evidence.
   No ARM deployment, RSS measurement, thermal test, hardware integration, or
   false-solve corpus has passed.

## Usability decision

Keep Astrometry.net as the production default. The independent solver may be
selected only in an explicitly bounded research run with a matching regional
catalogue; it remains unsuitable for unattended device use until the native
interface, all-sky index, false-solve gates, and ARM/resource gates are complete.

## Next required stage

The real Gaia regional catalogue stage and a fair same-frame Astrometry.net
comparison are now complete; see
[`dual-solver-gaia-20261028/SUMMARY.md`](evidence/dual-solver-gaia-20261028/SUMMARY.md).
Next: build the all-sky Gaia index and benchmark it before any device
selection.
