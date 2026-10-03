# Bulb review reconciliation — 2026-10-02

The external review was fair about the test and release-control gaps. The
reviewed `o-v15k` package was built from libgphoto2 `697907059`, but its
firmware-version literal was wrong and the package is withdrawn. The corrected
stock-based successor is `o-v15l-fwver-bulb-20261003-r2`.

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
- Full pre-release gate against the then-registered `o-v15k` package: 5 passed,
  0 failed, 0 skipped; Python suite 125 passed and deterministic suite 17
  passed.
- OpenPolaris `:shared:jvmTest :composeApp:jvmTest`: BUILD SUCCESSFUL.

These checks do not constitute physical camera qualification. The outstanding
live work is to run the canary with `--bulb-seconds` against an attached camera
and capture the command-268 option list, command-277 acknowledgement, command
264 lifecycle, and required file event. The current candidate is now 15l; the
15k firmware ZIP must not be staged.
