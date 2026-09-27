# o-v13e restored-fixes candidate

## Status

**BUILT, PRIVATELY PUBLISHED, PACKAGE-GATED; NOT INSTALLED; LIVE CANARY
PENDING.** This is one convergence candidate containing the recovered Pentax
fixes. No claim of live hardware qualification is made.

## Exact sources

- Patcher: `96b75902aae4473bfb7be56195fb3f9a079d73a9`
  (`release/o-v13d-review-convergence-20260926`, clean clone)
- libgphoto2: `564bdd070cec3f4a366444a7d7e95605f90e30f3`
  (`convergence/pentax-restored-fixes-20260927`, PR #94, clean clone)
- Test harness: `a8b65817354dae04f997d1357d7d4914e396c42f`
- Build id: `6.0.0.54.29-o-v13e-restored-fixes`
- Selected camlibs: `ptp2,pentax`
- Source dirty hashes: empty for both patcher and libgphoto2

The libgphoto2 delta restores strict-only admission, production-path virtual
publication lookup/list/delete semantics, exact seconds for long shutter
labels, timeout restoration on every abnormal capture exit and before
transfer, and timeout-phase diagnostics.

## Deterministic verification

- Focused libgphoto2 production-path tests: 4/4 PASS
  (`test-pentax-utils`, `test-pentax-reconcile`,
  `test-pentax-publication`, `test-pentax-aperture-alias`); `ptp2.so` compiles.
- Broader libgphoto2 Meson suite: 10/13 PASS. The three recorded failures are
  pre-existing environment/baseline failures: USB fixture parameters in
  `test-gp-port`, unknown generic model with a ptp2-only test setup in
  `test-gphoto2`, and the longstanding `test-filesys` SIGSEGV.
- Firmware-patcher offline gate: 13 container + 24 Python PASS; 0 fail/skip.
- Test harness: 62/62 PASS.
- Built-package gate: 13 container + 24 Python + structural validation +
  firmwareInfo validation PASS; 0 fail/skip.
- Full-stack build performed the ARM ABI, required-symbol, matched core/port,
  selected-camlib and manifest checks. The requested legacy selftest is
  intentionally inapplicable in full-stack mode because it targets the stock
  2.5.27 core; the stronger full-stack checks ran instead.

## Artifact and packaged-content proof

- Local artifact: `out/o-v13e-restored-fixes-20260927/FwPkt.zip`
- Private copy:
  `ian-morgan99/PrivateResearch/firmware-packets/o-v13e-restored-fixes-20260927/FwPkt.zip`
- Private artifact commit: `ac518690b`
- ZIP MD5: `5a3ae51583b4a46c02fd8120314a2bca`
- ZIP SHA-256:
  `4b7982e28e361f0669eedc61103e75f16a3101af0e47d79c3fdf500a65631c8d`
- appfs MD5: `f8e70314b4bf9c25d12ff4eaba16a4b9`
- `libgphoto2.so.6` MD5: `390194dd561de4bde4eb7ed701401507`
- `libgphoto2_port.so.12` MD5: `ad50e83594397aef48b63ed2375890cc`
- `ptp2.so` MD5: `f5dcdfe30840404e27fb0f526e3540d7`
- `pentax.so` MD5: `151750bae93f58801cd02176c6b38df9`
- `usb1.so` MD5: `4423bba29bf8c5d899598841ec3e6310`

The selected-camlib manifest inside the package records SHA-256
`02d3f4e2a7c88e47aa3cd612363abc0e90707e1aef4be3d9574b6ecf889e4597`
for `ptp2.so` and
`81fa3778f6d6a1daa4ee90d4ffe9ebeb31b01d1e620de0b77631771575780e36`
for `pentax.so`. This proves the package contains the newly built selected
camlibs, not merely that their source compiled.

## Remaining acceptance work

1. Install only through the documented complete-tree firmware update flow.
2. Cold reboot and prove FwVer, provenance, both core paths, camlib hashes and
   `/proc/<pgphoto>/maps` match this candidate.
3. Run the bounded one-shot canary, then the fail-closed two-shot gate with an
   independently established expected output count.
4. Record cancellation, Live View suspend/restore, external configuration
   generation and reconnect/rebind evidence as still unqualified where not
   physically exercised.
5. Resolve the independent atomic session-lock/rebind work in issue #146; this
   firmware does not claim that work is complete.

UVC devices remain out of scope for this package: selecting `ptp2,pentax`
preserves Canon and Pentax PTP plus legacy Pentax support, but iPolar and Orion
StarShoot require the separate V4L2/UVC integration tracked by issue #151.
