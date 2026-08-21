# Pentax capability target

The normative, source-reconciled IMAGE Transmitter 2 capability matrix is
maintained with the driver implementation:

- local development checkout:
  `../LibGphoto2/libgphoto2/docs/pentax/IMAGE_TRANSMITTER_CAPABILITY_MATRIX.md`
- cloud repository:
  <https://github.com/ian-morgan99/libgphoto2/blob/master/docs/pentax/IMAGE_TRANSMITTER_CAPABILITY_MATRIX.md>
- retrospective implementation/hardware audit:
  <https://github.com/ian-morgan99/libgphoto2/blob/master/docs/pentax/CAPABILITY_MATRIX_AUDIT.md>

Polaris packaging must target the exact libgphoto2 commit containing that
matrix and must not independently redefine camera capabilities. Camera-side
matrix tiers 0–12 are prerequisites for the corresponding Polaris tier 13
workflow.

Audited baseline: libgphoto2 commit `c82d19052`. The patcher’s clean-Git,
dirty-rejection/opt-in, reproducible dirty hash, source-archive, and unsafe
archive rejection preflight passed against that exact checkout on 2026-08-21.

The earlier 621-line extraction is preserved outside this repository at
`../LibGphoto2/archive/CameraCapabilities.extracted-obsolete-20260821.md`. It is
historical material only. It contains superseded claims, including an incorrect
K-3 Mark III USB identifier and K-1 II model flags, and must not be used as an
implementation or test target.
