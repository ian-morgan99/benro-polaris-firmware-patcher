# Polaris plate-solving master plan

Status: active implementation plan. The existing Astrometry.net path remains
the default and the independent native-C path is a research alternative. No
firmware or motor-control claim is made by a host build or a simulated solve.

The current end-to-end readiness review is [ASTRO-MISSION-READINESS.md](ASTRO-MISSION-READINESS.md).

## Objective

For every eligible JPEG captured by Benro Polaris Astro mode, preserve the
camera-side original, obtain a verified Polaris-side copy, resolve the frame
when policy permits, write a validated solve record into the Polaris-side
JPEG's EXIF, and make the result available to the Astro pointing/tracking
state. The eventual control loop should be able to use PrivateResearch Issue #3
(implementation tracked in patcher issue #240)'s independent
axis-rate interface when that firmware work is separately proven.

The two solvers are deliberately side by side:

| Path | Role now | Required evidence before it can replace the default |
|---|---|---|
| Astrometry.net front end | reference/default solver | existing package, licence/source offer, offline and device timing gates |
| Native independent C solver | alternative/research path | same-frame comparison, false-solve corpus, all-sky index, ARM resource test, camera-path test |

## Current reality and boundaries

- A transferred JPEG is not guaranteed merely because a capture was requested.
  The file must pass the existing descriptor, format, size, association,
  timeout and completion checks before it enters the solve queue.
- EXIF focal length is the first geometry source. Camera-model sensor width is
  the normal APS-C/full-frame fallback; explicit configuration is an override.
- RA/Dec from mount telemetry is a search accelerator, not proof. The solver
  must validate the image and fall back to a bounded corkscrew/all-sky search
  when the hint is absent or fails.
- A full solve is an absolute measurement. It must not be run synchronously in
  the capture path or used to issue motion without quality and freshness gates.
- The independent native path now has a packaged Gaia tile catalogue and
  triangle-ratio index. A focal length is still required; an RA/Dec hint is
  used first, with a bounded nearest-tile/all-sky fallback when the hint is
  absent or fails. This is host-tested and ARM-built, but not yet device
  qualified.
- The compact production index is currently strongest for the full-frame
  corpus. The K-3 III APS-C hinted path passes, while a narrow-field blind
  case exposed an index-coverage/runtime trade-off tracked in patcher issue
  #248; this is not a reason to widen the index without a renewed SD/runtime
  test.
- The current guide loop uses relative star matching and small GOTO corrections;
  it does not yet adjust motor rates.
- PrivateResearch Issue #3 (implementation tracked in patcher issue #240) is the intended per-axis rate-control path, but it is still a
  firmware-specific analysis/patch/qualification task. It must not be enabled
  from this plate-solving work until its exact-binary and hardware gates pass.

## Work sequence

### 1. Freeze the capture and solve contract

Document and test the actual flow:

```text
camera capture
  -> camera owns the original JPEG/RAW
  -> pgphoto publishes a completed JPEG candidate
  -> Polaris selects and copies the candidate to local SD
  -> admission checks pass
  -> solve queue records path, size, mtime, checksum and capture time
  -> EXIF focal/sensor metadata is resolved
  -> RA/Dec hint is read, if available
  -> selected solver runs with a hard timeout
  -> quality gates accept or reject the result
  -> local EXIF update is atomic and validated
  -> pointing/target state is updated only after the result is accepted
```

The camera SD original is never rewritten by the Polaris process. Any EXIF
update is to the verified Polaris-side copy unless a future, explicit camera
writeback feature is designed and qualified.

### 2. Establish the paired offline test

The immediate next pause is a reproducible same-frame comparison:

```sh
container/astro/compare-solvers.sh \
  --astro-dir out/dual-solver-host/astro \
  --index out/.astro-src-cache/astrometry.net-0.98/bench/index-4215.fits \
  --outdir out/dual-solver-test
```

This renders one JPEG with the existing sky shim, extracts one star list, and
feeds that same observation to both solver front ends. The independent leg
uses a synthetic catalogue derived from the known rendered scene; this proves
the binary/interface and matching plumbing, but explicitly does **not** prove
all-sky catalogue independence. The output records both JSON results and all
intermediate artefacts.

Because that synthetic catalogue is generated from the observed pixel list, its
reported rotation is not a fair independent roll measurement. The first fair
roll comparison is therefore deferred to the real Gaia-catalogue tier.

The real Gaia-derived regional tier is now exercised and caught a false
candidate caused by arbitrary source-ID catalogue truncation; the fix selects
the brightest eligible regional stars. See
[`dual-solver-gaia-20261028/SUMMARY.md`](evidence/dual-solver-gaia-20261028/SUMMARY.md).
The native host package now also contains the spatially partitioned Gaia tile
catalogue and triangle index, and the real-Gaia corpus exercises both hinted
and bounded blind search. A same-frame Astrometry.net comparison over that
real-Gaia corpus, plus device resource and capture-path measurements, remains
open.

### 3. Make the independent solver honest and useful

The native solver must progress through these gates:

1. hint-bounded regional solve with a real Gaia catalogue;
2. indexed tile loading rather than scanning the whole catalogue;
3. scale/rotation/parity and residual validation;
4. bounded corkscrew search around a stale hint, ordered by nearest tile;
5. all-sky blind search with focal-length scale bounds and indexed candidates;
6. calibrated JPEG distortion/noise tests;
7. ARM soft-float build, RSS, CPU, thermal and timeout measurements.

Every candidate must be rejected on ambiguous or weak evidence. A plausible
coordinate is not a solve without enough independent matches and a residual
margin over the next candidate.

### 4. Compare the solvers fairly

For every test frame, hold constant:

- JPEG pixels or the extracted star list;
- width, height, focal length and sensor geometry;
- RA/Dec hint and search policy;
- timeout and star cap;
- acceptance thresholds;
- scene ground truth and catalogue provenance.

Record success, absolute angular error, pixel scale error, roll error, parity,
matched stars, residual, wall time, peak RSS, catalogue bytes read and failure
reason. Include negative cases: wrong hint, wrong focal length, too few stars,
cloud/noise simulation, false catalogue candidates, and stale EXIF.

### 5. Integrate EXIF and pointing state safely

The EXIF writer must copy the JPEG to a temporary file, write only the owned
solve fields, reopen/validate the result, and atomically replace the local
copy. On any error the original local JPEG remains intact. A solve record must
include solver name/version, catalogue identity, timestamp, RA, Dec, roll,
scale, residual, match count, focal source, sensor source and quality verdict.

Pointing and target/rotation attributes are updated transactionally from an
accepted result. A failed or stale solve changes no motor target and does not
start tracking.

### 6. Add calibration and tracking feedback

Calibration should perform one or more absolute solves according to the
available UI. Repeated calibration solves can form a multi-point model, but
the current BenroConnect UI does not expose that selection; OpenPolaris or the
future Web UI must own the additional controls.

Once the independent-axis rate-control work in patcher issue #240 is qualified, the tracking loop becomes:

```text
accepted absolute solve
  -> relative star match per frame/live-view sample
  -> drift position + drift velocity
  -> bounded independent axis-rate update
  -> watchdog refresh or zero-rate fail-safe
  -> periodic absolute re-anchor on doubt or model change
```

Do not run a full solve for every JPEG merely to drive the rate loop. Full
solves may run asynchronously for validation, EXIF, and re-anchoring. Rate
commands require deadband, ramp limits, stale-frame timeout, integral-windup
protection, link-loss stop, and a dry-run/log-only mode before live enablement.

## Acceptance gates

The project must keep these verdicts separate:

`SOURCE-BUILT` → `HOST-PAIRED` → `FALSE-SOLVE-TESTED` → `ARM-BUILT` →
`DEVICE-OFFLINE-QUALIFIED` → `CAPTURE-PATH-QUALIFIED` →
`EXIF-QUALIFIED` → `POINTING-QUALIFIED` → `RATE-CONTROL-QUALIFIED`.

The current work has passed source, host-paired, false-solve, ARM-build, and
host EXIF smoke gates for the native path. It is not yet at
`DEVICE-OFFLINE-QUALIFIED`, `CAPTURE-PATH-QUALIFIED`, `POINTING-QUALIFIED`, or
`RATE-CONTROL-QUALIFIED`.

## Immediate deliverable at the next pause

The next pause should contain:

- a built native independent solver and native sky shim;
- one generated JPEG and its extracted star list;
- one Astrometry.net JSON result;
- one independent-solver JSON result;
- the command, binary hashes, catalogue manifest and timing;
- a host real-Gaia indexed corpus result plus negative-search results;
- canonical Debian 9 ARM build and staged-package evidence;
- an explicit statement that device capture/EXIF/pointing and rate-control
  qualification remain open.

See [DUAL-SOLVER.md](DUAL-SOLVER.md), [INDEPENDENT-SOLVER-USABILITY-AUDIT.md](INDEPENDENT-SOLVER-USABILITY-AUDIT.md), and
[PLATE-SOLVE-CAPTURE-FLOW.md](PLATE-SOLVE-CAPTURE-FLOW.md) for the current
runtime and safety details.
