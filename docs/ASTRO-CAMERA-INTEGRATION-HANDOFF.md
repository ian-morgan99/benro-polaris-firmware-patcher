# Astro / standard-camera integration handoff

Review date: 2026-11-03

This branch owns the separate Astro candidate. Its camera implementation is
the standard camera implementation at the accepted baseline; Astro adds only
the native-C solver, catalogue/index bundle, orchestration and research UI.

## Provenance and ownership

| role | worktree/ref | state |
|---|---|---|
| Astro owner | /home/ian/Documents/VSCodeProjects/BenroPolarisPatcher, feature/astro-native-platesolve | dirty local checkout intentionally preserved at 8626bfd; it is behind the pushed clean integration and still contains another agent's edits |
| integrated Astro source | feature/astro-native-platesolve | pushed merge fb29e933, then gate fix e725db2, candidate tooling f11cef9 |
| standard camera baseline | /home/ian/polaris-build-73 main | 397320411a1355f06d21233435e144d24efc4207; source fixes are merged, physical qualification remains pending |
| libgphoto2 input | clean main checkout | pinned at 43dccb81b92b6b25f44957a4684f534393562028 |

The adjacent LibGphoto2/libgphoto2 checkout is a different feature branch
and is not an accepted input. No deployment or device mutation has occurred.

## What was transferred

The clean v94 staging worktree merges current standard main into Astro with
merge commit 82415ab0 (the exact pushed SHA is recorded in the v94 release identity). Shared camera/release paths were
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

scripts/build-astro-candidate.sh is the controlled build-only entry point. It now requires a human change summary and:

1. requires a clean feature/astro-native-platesolve checkout containing
   standard camera baseline 39732041...;
2. requires clean libgphoto2 main at 43dccb81...;
3. invokes the same patch-polaris.sh FwPkt path as standard firmware;
4. builds the additive astro-bundle/ with native C binaries, Gaia tiles,
   selected Astrometry.net FITS indexes and corresponding source;
5. generates the immutable install manifest;
6. runs the shared camera gate against that FwPkt and the Astro suites;
7. writes astro-candidate-manifest.json with source, dependency, packet and
   catalogue hashes;
8. writes and verifies release-change-manifest.json and RELEASE-IDENTITY.md,
   including the release SHA in the final provenance.

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

- The standard camera fixes are now merged from main. The v94 source/package
  gates do not replace supervised physical qualification of #251, #253, or the
  Astro camera lifecycle.
- Candidate build and publication are complete; hashes are recorded in
  astro-candidate-manifest.json and the PrivateResearch README.
- Coordinate one supervised hardware window. Use only the documented
  Bluetooth-wake/ZIP-tree install path; never use SCP or manual SSH code
  replacement.
- Qualify camera lifecycle, transferred JPEG publication, solve accuracy,
  EXIF writeback, calibration/GOTO, drift detection and motor-rate safety
  separately. Compilation, emulator and synthetic solves are not physical
  qualification.
