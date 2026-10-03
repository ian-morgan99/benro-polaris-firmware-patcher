# o-v15p 15G-semantic capture recovery candidate

Status: candidate built and privately archived; not installed; physical camera test pending.

## Provenance

- patcher `main`: `02fa2f07663edcf5f7176a00532f56cd8aadb00c`
- libgphoto2 `main`: `52196d9f16450bc5a3a234330e2bec6a472ffc8b`
- build id: `6.0.0.54.53-o-v15p-15g-recovery`
- display firmware version: `6.0.0.54.53`
- built from: original stock `firmware/FwPkt.zip`
- PrivateResearch commit: `6c0ed67ab`
- private artifact: `firmware-packets/o-v15p-15g-recovery-20261003/FwPkt.zip`
- ZIP MD5: `51a112b8fc77b2386d6cf2614395918a`
- ZIP SHA-256: `fcf815562c07ecf21a003e53f6405c45762bcfb9b51c50c77bf3324154f8ec3c`
- appfs MD5: `4b1ed228617bcb5e63a85c6779b47ddc`

## Behavioural delta

- Ordinary Manual and camera-timed Bulb call an explicit Pentax
  `InitiateCapture(release=0)` helper.
- The K-3 III/K-3 III Mono research release-mode-2 path remains blocked.
- The 15G pre-capture conditions snapshot and duration-aware wait budget remain
  in the timed path.
- RAW+JPEG reconciliation accepts only a same-basename, different known image
  format when a companion is required; unknown or ambiguous candidates remain
  on the camera and block safely.
- Firmware Bulb pre-shot-delay and exact display-version patches remain in the
  package.

## Offline results

- libgphoto2 applicable Meson tests: **15 passed, 0 failed**. The separate
  `no-ci:test-gp-port` test is environment-dependent and is not part of the
  applicable release pack.
- patcher pre-release gate: **4 passed, 0 failed, 1 prerequisite skip**. The
  skip is the clean-checkout stock-manifest prerequisite; the release build
  and private-upload manifest checks passed.
- PrivateResearch upload: **PASS**, exact ZIP hashes above were recomputed from
  the uploaded build and the upload commit is `6c0ed67ab`.

## What this does not prove

The 2026-10-03 physical log was from installed o-v15i and used `bulb:0`; it is
not evidence for this candidate and did not prove a non-zero Bulb capture.
This candidate has no hardware qualification yet. The required physical order
is M shot 1, M shot 2, timed B 4 s natural, M, timed B 10 s natural, longer B
with explicit stop, M, then two RAW+JPEG shots. If Manual shot 1 or shot 2
fails, stop and preserve the Mlog/Clog before testing Bulb.
