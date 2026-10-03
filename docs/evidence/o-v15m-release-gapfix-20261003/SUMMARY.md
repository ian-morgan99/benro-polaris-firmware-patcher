# o-v15m release-control and Bulb-canary candidate

Status: **BUILT; PRIVATELY ARCHIVED; NOT INSTALLED**

This is a stock-based rebuild after the adversarial review of the 15k/15l
version and Bulb test controls. It does not claim physical camera support.

## Changes

- The code-780 format literal is calculated once in
  `container/polestar_fwver_patch.py`; the repackaging assertion and regression
  test import that value instead of duplicating it.
- One-shot, two-shot, and Astro Bulb canaries restore the exact shutter index
  that was active before the test, including failure paths.
- Bulb duration and shutter-index arguments now fail closed when no capture is
  requested.
- The live canary can assert the exact code-780 `sw` response with
  `--expected-sw`.
- The formal release script now runs the parameterised display-version package
  test from the original stock FwPkt tree.
- Historical 15k evidence now clearly records that 15k is withdrawn.

## Build identity

- Candidate: `o-v15m-release-gapfix-20261003`
- Build ID: `6.0.0.54.52-o-v15m-release-gapfix`
- Patcher `main`: `9e510132cfa7023c8b195eb28a571bfa020bdc56`
- libgphoto2 `main`: `e0e5135023165b9a4411bba637076b8ca1e63ed1`
- Display/FwVer: `6.0.0.54.52`
- PrivateResearch artifact commit: `ac125ae6f`
- PrivateResearch path: `firmware-packets/o-v15m-release-gapfix-20261003/FwPkt.zip`

## Artifact hashes

- ZIP MD5: `0547dd258102df09501bfa8ce669e810`
- ZIP SHA-256: `308bc9b335b04a2dfe775d4e48a64c5db879ee7b22eacca6f7212ed76bc5e8b2`
- appfs MD5: `c05ec7dd0c47693c6308ff746b6c9213`

## Verification

- libgphoto2 regression pack: `14/14` passed
- parameterised package/display-version test from stock: **passed**
- patcher deterministic harness: `17` passed
- Python regression suite: `129` passed
- FwPkt structural and shipped `firmwareInfo` checks: **passed**
- pre-release gate: `4` passed, `0` failed, `1` skipped because the clean
  release checkout has no stock manifest; the private upload independently
  revalidated the exact shipped archive and manifest
- physical Polaris installation/camera validation: **NOT TESTED**
