# o-v15k firmware-version candidate — withdrawn

Status: **WITHDRAWN — INVALID VERSION PATCH; DO NOT STAGE**

15k was initially described as the corrected successor to withdrawn 15j, but
that description was wrong. Its code-780 literal is `0x0091779c`, which the
ADD at `0x13fb84` resolves to `0xa57328`, four bytes into the date format
instead of the standalone `%s` at `0xa57324`. Benro Connect consequently saw
an unusable version and displayed `null`. Keep this artifact as historical
evidence only. The corrected successor is 15l.

## Build identity

- Candidate: `o-v15k-fw-version-20261002`
- Build ID: `6.0.0.54.52-o-v15k-fw-version-fixed`
- Patcher `main`: `23f49297ce0de0d03b88075be73e76fdf753cde5`
- libgphoto2 `main`: `6979070597ebddbaa5f1cff1e56b7597e4594ed2`
- Display/FwVer: `6.0.0.54.52`
- PrivateResearch: `firmware-packets/o-v15k-fw-version-20261002/FwPkt.zip`
  (artifact commit `d3870b5ea`)

## Artifact hashes

- ZIP MD5: `11efec0431cfd0d705c554d3703c0453`
- ZIP SHA-256: `00e32619f89400ff5d25a86822e241dd1d1d0f56d6dd9dbec0bbd859c068bff0`
- appfs MD5: `ee2a37205404f59abd90a05b1a9ed377`

## Validation

- libgphoto2 regression pack: `14/14 passed`
- pre-release gate: `4 passed, 0 failed, 0 skipped`
- firmware package and `firmwareInfo` manifest gates: passed
- corrected version patch on the actual extracted appfs: passed
- idempotent patch test: passed
- Bulb patch survived appfs repack: passed

The candidate was not installed and has no physical camera qualification. It
is superseded by `o-v15l-fwver-bulb-20261003-r2`.
