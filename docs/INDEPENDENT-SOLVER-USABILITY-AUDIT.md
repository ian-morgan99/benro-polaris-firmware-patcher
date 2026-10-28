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
- Sixteen deterministic tests pass.
- Native C tile-search front end with bounded hint/corkscrew and triangle-index
  all-sky candidate policy; no Python runtime is required on the device path.
- Saturation-safe 0.1% triangle-ratio queries; observed triangles whose ratio
  cannot be represented in the on-disk key are discarded instead of being
  folded into the 65535 saturation bucket.

## Native-C tuning pass

The first native-C implementation has now had a bounded tuning pass. It still
uses the same catalogue format and command-line contract, but:

- catalogue pair distances are cached once instead of recomputed for every
  observed/catalogue triangle;
- only the brightest 15 observations are used as triangle anchors by default,
  while all accepted observations remain available for verification;
- duplicate observations can no longer count against the same catalogue star;
- accepted candidates are re-fitted using all unique inliers, then scored by
  match count and RMS residual rather than match count alone;
- the device search path uses a 120-record catalogue cap and 10 anchor stars
  to retain sparse-field matches without returning to the slower 15-anchor
  brute-force setting;
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
not as a reason to change the production default. A multi-frame error
distribution and real camera frames are still required.

## Blocking limitations

1. The independent solver and sky renderer now have native C host/ARM build
   paths, and the runtime selector supplies the tile/index catalogue arguments.
   The paired harness has run successfully on one host frame.
2. The native solver still requires a spatially partitioned catalogue and
   triangle index and the native search front end is bounded; it is not yet a
   production-scale blind all-sky qualification. A corrected host smoke over
   648 tiles and a 294,840-record triangle index solved the real-Gaia regional
   frame plus four independent Gaia-rendered scenes, but this remains rendered
   frame evidence.
3. The all-sky candidate index is a compact triangle-ratio lookup, not a full
   descriptor database. It still needs wrong-solve and real-camera error
   distributions before unattended use.
4. The Gaia data currently used is a G<=10 research package. The bundle builder
   can now carry its tile/index package, but no ARM device bundle has been
   installed or qualified. Source, tile, and index checksums are recorded in
   [the native-search evidence](evidence/native-search-20261028/SUMMARY.md).
5. The native independent renderer has no camera distortion,
   vignetting, saturation, or colour/noise calibration.
6. The first paired run uses a synthetic catalogue derived from the known test
   scene. The additional Gaia scenes use the real downloaded Gaia tile set, but
   are still rendered frames. No ARM deployment, thermal test, hardware
   integration, or false-solve corpus has passed. The five-scene host search
   smoke used 4.8 MB peak RSS and 13.1 s for its five-attempt regional run.
7. The standalone native C sources cross-compile, but the current host ARM
   toolchain emits `__libc_start_main@GLIBC_2.34`; a glibc-2.24 sysroot or
   equivalent startup/runtime solution is still required. See
   [the ARM toolchain evidence](evidence/native-arm-toolchain-20261028/SUMMARY.md).

## Usability decision

Keep Astrometry.net as the production default. The independent solver may be
selected only in an explicitly bounded research run with a matching indexed
catalogue; it remains unsuitable for unattended device use until the false-
solve, ARM/resource, and physical capture gates are complete.

## Next required stage

The real Gaia regional comparison and host all-sky indexed-search smoke are
complete; see
[`dual-solver-gaia-20261028/SUMMARY.md`](evidence/dual-solver-gaia-20261028/SUMMARY.md)
and [`native-search-20261028/SUMMARY.md`](evidence/native-search-20261028/SUMMARY.md).
Next: qualify the ARM sysroot and package/resource contract, then run a
wrong-solve and real-camera capture matrix before any device selection.
