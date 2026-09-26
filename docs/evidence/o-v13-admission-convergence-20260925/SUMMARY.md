# o-v13 admission convergence candidate

Status: **BUILD-VALIDATED; NOT INSTALLED; CAMERA ACCEPTANCE PENDING**

## Exact inputs

- patcher: `1c1d386f66d1a77686d59762be2468aa6601c800` (clean worktree)
- libgphoto2: `50ba504152fe5c7bc8d3576acc4b643828db1de8` (clean standalone clone)
- harness: `a8b65817354dae04f997d1357d7d4914e396c42f`
- build mode: full matched stack, libgphoto2 2.5.34 paths, libgphoto2_port 0.12.2 paths, 256 MiB Pentax capture cap, self-test requested (documented full-mode skip), no polestar Bulb patch
- build id: `6.0.0.54.24-o-v13-admission`

The libgphoto2 branch contains the reviewed convergence lineage from
`c57a8a3ac` through output publication/reconciliation and companion ownership,
plus commit `50ba50415` adding a runtime-selectable admission discriminator.
Default `strict` behavior preserves the fail-closed +104 activity gate.
`PENTAX_ADMISSION_MODE=output-safe` ignores only broad +104 activity after a
complete conditions read while continuing to require no active exposure (+32)
and no pending candidate (+36). Both results are logged on every recovery probe.

## Deterministic evidence

- libgphoto2 focused production/helper tests: 2/2 PASS
- harness full suite: 62/62 PASS
- patcher offline gate: 12 container checks + 15 Python tests PASS
- package gate: container, Python and FwPkt structural checks PASS
- package-gate stock-manifest check: SKIP because the clean public worktree has
  no stock firmware bytes; the build and private-upload gates independently
  re-hashed all six `firmwareInfo` entries and passed

## Artifact and embedded stack proof

- artifact: `FwPkt.zip`
- zip MD5: `c942d305334e8e267d5296b5b3f21b4a`
- zip SHA-256: `806bc836c54b70fc9bd924a06424d6332d030cc93088b41e0b7764269bbf5032`
- appfs MD5: `847cdf7a48bdbdc894268047cd18f63a`
- appfs SHA-256: `45a3133a375968395b1e1c49683f731539e5fb62fe76b13d2df1a63b7817e8e0`
- extracted ptp2 SHA-256: `2a65300330d2eb468ba2fc4f704cce12f5ea55f25bac2aadcf5134d4eb04da31`
- extracted core SHA-256: `e5c1d90fd474a24b6dbb04cfffca4ac85ca05d68b43758f1a696eba8821e8bfe`
- extracted port SHA-256: `e9e979be616eebd93551e58c9ced1a99d7a247a195bf5b6a57a819358c482b67`
- extracted usb1 SHA-256: `4d4bfe4863508dd33aeb1276c5eb1c887845aa7fdf1644299853a760a097dd0e`
- extracted pgphoto.stage2ondisk SHA-256: `00d8e9e80e2813ddf2c89d28f219de33a09b1fde17dd20f7f2590793fb6df81d`
- extracted libpolaris_stage2.so SHA-256: `92f88ed8967fd3dd29e019f7566a5d555924ad62561b5a0072948fc8b2fb250a`
- extracted wrapper SHA-256: `68c1ebf569bd37fe7eb349a725ad869a44a3de2be186da4799b3780f2ac3dfa0`

Independent UBIFS extraction proved the embedded `ptp2.so` byte-matches the
build output; Stage-2 and stock core copies match; Stage-2 and stock port copies
match. Embedded provenance names the exact patcher/libgphoto2 commits and clean
source state. The diagnostic strings `PENTAX_ADMISSION_MODE`, `output-safe` and
the full admission correlation format are present in the shipped camlib.

Private bytes: `ian-morgan99/PrivateResearch` commit `e7e8f0dc8`, path
`firmware-packets/o-v13-admission-convergence-20260925/FwPkt.zip`.

## Minimum physical acceptance

Install only through the sanctioned FwPkt flow. After cold boot, prove runtime
hashes/maps and one pgphoto owner. With one deliberate client and preview off:

1. capture one ordinary RAW or JPEG and require a published code-773 file;
2. issue the second capture while recording capture ID, +32, +36, +104, strict
   and output-safe decisions, output obligation/publication and actual
   `InitiateCapture` result;
3. compare default strict admission with `PENTAX_ADMISSION_MODE=output-safe`
   using the same installed bytes and workflow;
4. stop immediately if output-safe admits a shutter that returns CAMERA_BUSY or
   damages the session; otherwise record the first +104 divergence that still
   permits a successful second shutter;
5. exercise cancellation once during an admission wait.

This answers only the minimum safe next-shutter predicate. It does not qualify
the broader #149 physical matrix, K-1 II, Canon R5 II, or OpenPolaris E2E.
