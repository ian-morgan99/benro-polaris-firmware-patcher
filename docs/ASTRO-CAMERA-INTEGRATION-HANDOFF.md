# Astro / standard-camera integration handoff

Review date: 2026-11-01

This branch owns the separate Astro candidate. Its camera implementation is
the standard camera implementation at the accepted baseline; Astro adds only
the native-C solver, catalogue/index bundle, orchestration and research UI.

## Provenance and ownership

| role | worktree/ref | state |
|---|---|---|
| Astro owner | /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher, feature/astro-native-platesolve | dirty local checkout intentionally preserved at 8626bfd; it is behind the pushed clean integration and still contains another agent's edits |
| integrated Astro source | feature/astro-native-platesolve | pushed merge fb29e933, then gate fix e725db2, candidate tooling f11cef9 |
| standard camera baseline | /home/ian/polaris-build-73 main | 8c015c0a73c8affea8fa723badcceb4070ef81b4; issue #251 remains release-blocking and not physically qualified |
| libgphoto2 input | /home/ian/Documents/VSCodeProjects/LibGphoto2-v86-main main | clean, pinned at 051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff |

The adjacent LibGphoto2/libgphoto2 checkout is a different feature branch
and is not an accepted input. No deployment or device mutation has occurred.

## What was transferred

The clean staging worktree merged standard main into Astro with
fb29e93324e831dd78e76f4be2f198ed39f4c8d2. Shared camera/release paths were
taken from standard main, including the Stage-2 loader and release/gate
scripts. The resulting diff against main contains no camera-adjacent files:
Astro differences are confined to the Astro sources/tools/tests/docs and the
build-only candidate tooling. This is a source integration, not camera
qualification.

The dirty owner checkout was never stashed, reset, rebased, merged over, or
used for a release build. Its uncommitted container/stage2_loader.c,
release scripts, harness evidence and related files remain with their owner.
The owner was notified on issue #251; Astro did not independently fix or retain
a competing #251 implementation.

## Candidate contract

scripts/build-astro-candidate.sh is the controlled build-only entry point. It:

1. requires a clean feature/astro-native-platesolve checkout containing
   standard camera baseline 8c015c0a...;
2. requires clean libgphoto2 main at 051d224d...;
3. invokes the same patch-polaris.sh FwPkt path as standard firmware;
4. builds the additive astro-bundle/ with native C binaries, Gaia tiles,
   selected Astrometry.net FITS indexes and corresponding source;
5. generates the immutable install manifest;
6. runs the shared camera gate against that FwPkt and the Astro suites;
7. writes astro-candidate-manifest.json with source, dependency, packet and
   catalogue hashes.

The script never stages, reboots, flashes or uploads. Publication is a
separate, explicit action. The Astro bundle is not linked into Stage 2; it is
installed from SD only after supervised review. No live motor-rate command is
enabled.

## Evidence so far

- Final candidate Astro suite: 75 passed, 6 skipped.
- Final shared gate: 430 Python tests and 15 checks passed; 0 failed, 2 prerequisite skips.
- FwPkt SHA-256: 7c11f9a033b2372f1215aca89e3f6ac46544047f26802fe94a68b77217be01d2.
- Astro bundle SHA-256: 40fe08e7c87e24d5e30fb42660afc917d4ad0df1d227617ac8bfc62d6b0b9a13.
- Published at firmware-packets/6.0.0.54.91--astro-v1-camera-baseline-20261101 in PrivateResearch, commit b298b601a.
- The skips were stock firmwareInfo cross-check, previous-candidate
  differential, and provenance registry comparison because the public
  checkout has no stock ZIP/previous manifest. They are recorded, not treated
  as passes.
- A narrow 50 mm APS-C index set was downloaded to /tmp for testing:
  4114 through 4118, 2.8 MB. The candidate builder can select the same range
  from focal length and sensor width.
- No physical Polaris, camera, install, tracking or safety qualification has
  been performed.

## Remaining gates

- The standard camera owner must resolve/accept #251 and provide the final
- Candidate build and publication are complete; hashes are recorded in
  astro-candidate-manifest.json and the PrivateResearch README.
  astro PrivateResearch path, and record the exact manifest hashes.
- Coordinate one supervised hardware window. Use only the documented
  Bluetooth-wake/ZIP-tree install path; never use SCP or manual SSH code
  replacement.
- Qualify camera lifecycle, transferred JPEG publication, solve accuracy,
  EXIF writeback, calibration/GOTO, drift detection and motor-rate safety
  separately. Compilation, emulator and synthetic solves are not physical
  qualification.
