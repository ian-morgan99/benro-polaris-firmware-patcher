# Bulb review reconciliation — 2026-10-02

The external review was fair about the test and release-control gaps. It was
not correct that the current `o-v15k` package predates libgphoto2 `697907059`:
that package was built from that exact libgphoto2 commit and the corrected
patcher commit `23f4929`.

## Corrections made

- The Bulb canaries now read command 268's live shutter option list and locate
  the single `Bulb`/`B` entry. An explicitly supplied index is accepted only
  when it matches that live entry; guessed indices fail closed.
- Command 277 now requires an explicit `ret:0` acknowledgement. Missing or
  non-zero acknowledgements are failures.
- One-shot, two-shot, and Astro canaries share the same timeout calculation,
  which allows the requested Bulb hold and post-capture lifecycle.
- The package gate extracts the actual repacked `polestar_app` from the build
  and verifies the firmware-side Bulb patch marker. It does not trust the
  patch script or build log alone.
- OpenPolaris Manual Bulb now checks the `PhotoRecordResult`; it reports a
  rejected command instead of displaying a successful capture when the
  camera does not echo `state:1`.

## Verification

- Patcher focused Bulb tests: 99 passed.
- Full pre-release gate against the registered `o-v15k` package: 5 passed,
  0 failed, 0 skipped; Python suite 125 passed and deterministic suite 17
  passed.
- OpenPolaris `:shared:jvmTest :composeApp:jvmTest`: BUILD SUCCESSFUL.

These checks do not constitute physical camera qualification. The outstanding
live work is to run the canary with `--bulb-seconds` against an attached camera
and capture the command-268 option list, command-277 acknowledgement, command
264 lifecycle, and required file event. The current `o-v15k` firmware ZIP was
not changed by this review; the canary and UI fixes are source changes for the
next release candidate.
