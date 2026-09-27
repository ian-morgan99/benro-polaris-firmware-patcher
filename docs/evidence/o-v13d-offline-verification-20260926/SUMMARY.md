# o-v13d offline verification — 2026-09-26

Status: **BUILD + PACKAGE evidence only.** No Polaris boot, no camera attach,
no capture. The `-108` fix (issue #145) is proven in source and deterministic
regression; physical canary still owed after install.

## Identities

| item | value |
|---|---|
| libgphoto2 source | `4074b6b0b0fdc2b6dd3f60c0aa6d4310a924cb44` (PR 90 head, clean detached checkout) |
| patcher source | `c5321c4e67053e696808451370cc3de7ff2089a6` (`release/o-v13d-review-convergence-20260926`) |
| build id | `6.0.0.54.28-o-v13d-publication-fix` |
| FwPkt.zip SHA-256 | `458cb3b6fe99fa59bba6a9d0326a6a838c94cb3224ad2cd458681b38d11422b5` |
| selected camlibs | `ptp2,pentax` (both in `camlibs.manifest`, hash-verified) |
| test-harness contract | `a8b658173` |

The staged build lives in the codex worktree
`/tmp/polaris-patcher-o-v13d.7qx1k9/out/o-v13d-publication-fix-20260926`.
PR 90 (`fix/pentax-capture-publication-145`) is OPEN and mergeable; o-v13d
embeds it pre-merge, so the release record cites the SHA, not the branch.

## Gate results (all run 2026-09-26 16:10–17:15 UTC)

1. **Independent rebuild** — `container/test_polaris_pentax_build_package.sh`
   from the release branch, against a fresh clean clone of `4074b6b0b` and the
   stock FwPkt (`firmware/FwPkt.zip`): `polaris-pentax end-to-end: PASS`.
   The docker image used (`polaris-patcher`, built 2026-09-26 15:18) was
   verified byte-identical to the release-branch `container/` scripts
   (sha256 of `build_ptp2.sh`, `patch.sh`, `stage2_loader.c` match), so the
   build ran the exact release-branch tooling.
2. **Pre-release gate** — `./tests/run_prerelease_gate.sh --build out/o-v13d-publication-fix-20260926/FwPkt`:
   - PASS: container deterministic harness (13 passed)
   - PASS: python regression suite (24 passed)
   - PASS: FwPkt structural validation
   - PASS: firmwareInfo manifest gate (stock manifest vs o-v13d build)
   - **GATE: GREEN — 4 passed, 0 failed, 0 skipped**
3. **Test-harness contract `a8b658173`** — 62 passed.
4. **Marker audit of the staged payload** (codex's own build output): all nine
   ptp2 markers present in `stage2-ondisk/libgphoto2/2.5.34/ptp2.so`,
   including `Serving retained Pentax capture publication generation` (the
   #145 fix), the five `boundary=*` capture checkpoints, and both K-1 II /
   K-3 III model strings; core `[libgphoto2] gp_camera_capture: enter`
   checkpoint present in `libgphoto2.so.6`; `sha256sum -c camlibs.manifest`
   OK for `ptp2.so` + `pentax.so`.

## Remaining physical qualification (owed)

- Install o-v13d on the Polaris; re-prove identity (BSSID, route, FwVer,
  matched-stack hashes, loader maps).
- K-3 III attached, RAW-only contract:
  `./tests/run_prerelease_gate.sh --canary --expected-files 1` — expect a
  completed exposure without the late `-108`.
- Then the two-shot gate (`--two-shot --expected-files 2`) for the
  same-session repeated-shutter path.

Issue #145 checkpoint comment:
https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/145#issuecomment-5847845535
