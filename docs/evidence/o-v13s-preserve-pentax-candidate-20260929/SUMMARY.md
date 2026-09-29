# o-v13s candidate — preserve unresolved Pentax transfer candidate

Status: **built and package-gated; not installed; independent review and physical test pending.**

## Plain-English change

If Pentax has offered an image and a later transfer/publication step fails, the
driver no longer deletes that camera-side candidate as generic cleanup. It
marks the session recovery-required. The existing admission gate still blocks
the next shutter while the candidate remains unresolved.

This does **not** publish the orphan into Benro Connect. It also does not
explain the observed SP_0136 incident: the log showed `InitiateCapture`
accepted, but no candidate/completion was observed before pgphoto exited.

## Exact inputs and artifact

- Patcher: `d11bc748f917a1705988596aa6acf565a7131c9a`, `main`, clean.
- libgphoto2: `204c2a95a0da78135ad3c6dc244c230d5d16d2e9`, `main`, clean.
- Stock FwPkt: `firmware/FwPkt.zip` (input to the canonical release script).
- Build id: `6.0.0.54.35-o-v13s-preserve-pending`.
- Candidate ZIP: `o-v13s-preserve-pentax-candidate-20260929/FwPkt.zip`.
- ZIP MD5: `744815412b9acc51fba01fc0b01a782f`.
- ZIP SHA-256: `6f02b20cb1d3e5f27ed99cb4b3f800adb4827dd65396d39fda7c188bb7d70b7b`.
- AppFS MD5: `889a34781e04edcfd11af38a432a46ee`.
- PrivateResearch commit: `3b4693748244636ffe2aaaddd5be30893f790f0a`.
- Selected camlibs: `ptp2,pentax`.

The deterministic package test checks the components embedded in appfs against
the generated Stage-2 runtime bundle; the bundle includes `ptp2.so`,
`pentax.so`, `usb1.so`, both libgphoto2 libraries and the camlibs manifest.

## Tests

- libgphoto2 canonical clean regression build: passed; selected tests and
  production `ptp2.so` build passed. The release script explicitly skipped the
  no-CI serial-control test (`test-gp-port`) because no supported DTR/CTS
  fixture exists.
- Patcher deterministic + Python + package structure + firmwareInfo manifest:
  **4 passed, 0 failed, 0 skipped**.
- Harness repository full suite: **62 passed** at
  `0355f6f643ae7c154ea42a2f751d14fa1dbcb135` (unchanged `main`). This validates
  synthetic protocol/runtime contracts only, not Pentax hardware behavior.
- The aggregate patcher deterministic runner reports **14 passed, 0 failed,
  2 skipped**. Its optional container rebuild test was skipped because its
  Docker image/source arguments were not supplied; the release build itself
  ran from the exact clean source SHA. Separately, the built appfs was extracted
  from the produced package and 10 runtime files plus embedded provenance were
  byte-compared against the generated Stage-2 bundle; all matched. See
  `package-content-verification.txt`.
- Separate existing local `_build` full Meson run was 12/14. Failures were
  `no-ci:test-gp-port` (host USB/serial environment) and `test-gphoto2`
  (`Unknown model` with that local build configured without the research-only
  camera model). Neither test was disabled or weakened; the canonical release
  script's clean selected regression build passed.
- No physical test has been run on this candidate. No claims are made for
  Benro Connect, Astro, Panorama, RAW-only, JPEG-only, RAW+JPEG, or Pixel Shift.

## Required next validation

Independent review must inspect the exact two source SHAs, package test
evidence, registry row and PrivateResearch ZIP hashes before any install.
After review, install only through the documented FwPkt update procedure and
test an intentional failure/recovery case only if the camera/operator can
observe the corresponding candidate state. A normal capture pass alone will
not test this error-path change.
