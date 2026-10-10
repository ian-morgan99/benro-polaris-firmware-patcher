# o-v16f Bulb branch-audit candidate — 2026-10-10

## Result

**Disposition: DO NOT STAGE.** Built and privately archived a **diagnostic candidate**, not a complete Bulb fix. The candidate omits the retired `polestar_app` patch that set `bulb_ms` to zero. The package gate confirms the original non-zero Bulb request branch remains intact. This removes a known harmful rewrite; it does **not** connect the request to the held-Bulb action or prove the camera fires through Polaris.

No firmware was installed, and no Polaris or physical camera test was run. Do not describe this candidate as Bulb-qualified.

## Provenance

- Candidate: `o-v16f-bulb-branch-audit-20261010`
- Display version / build ID: `6.0.0.54.64` / `6.0.0.54.64-o-v16f-bulb-branch-audit-20261010`
- Patcher source: [`fb20128048b8980305a33b489fd266873a629d3e`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/fb20128048b8980305a33b489fd266873a629d3e), `main`
- libgphoto2 source: [`41fb0826a026d0d4b2fe05c0221f8468f504208d`](https://github.com/ian-morgan99/libgphoto2/commit/41fb0826a026d0d4b2fe05c0221f8468f504208d), `main`
- Stock FwPkt: `firmware/FwPkt.zip`; MD5 `90bdad511f556f25a2904ae9d2980102`; SHA-256 `f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f`; appfs MD5 `47f2ae680be3a5f5d69aa20e20a2397b`
- Candidate FwPkt: MD5 `e5fc9735165ad6ce928ad11829b7e03a`; SHA-256 `e26cd48f38f13ca53537cb24b46bd5b4fb41cce2c20c8b72325834287175ebbf`; appfs MD5 `5e8faf6f9493f31a9f3689ca0280ea07`
- PrivateResearch ZIP commit `f409d5686`; `firmware-packets/o-v16f-bulb-branch-audit-20261010/FwPkt.zip`. Its warning-only README update is commit `4f49da039`; the ZIP bytes and hashes are unchanged.

## Validation

- libgphoto2 regression pack in the release build: passed; CI-only DTR/CTS test excluded by the documented `no-ci` selector.
- Patcher pre-release gate: 8 passed, 0 failed, 0 skipped.
- Deterministic container tests: 19 passed.
- Python regression suite: 211 passed.
- Package structure and `firmwareInfo` MD5/size manifest: passed.
- Repacked appfs audit: original Bulb branch intact; retired zeroing sequence absent.
- Full build/upload transcript: [build-release-candidate.txt](./build-release-candidate.txt); normalized to LF with trailing whitespace trimmed for repository hygiene.

## Remaining defect and qualification boundary

Static follow-up in stock `pgphoto` confirms code 264 calls `captureImage` (`0x1741c`), while `captureBulbImage` (`0x20604`) has no callers. `captureImage` reads `bTime` and passes it as `continuous` to `capture_image_with_Burst` (`0x20bc0`). The explicit positive-`continuous` setting branch is guarded by `checkCameraVerdor(1)`, which resolves to `nikon`, and formats `burstnumber=%d`; the vendor table contains no Pentax entry. That is not evidence of a Pentax Bulb shutter action. The production build also leaves the research-only libgphoto2 held action disabled.

**Do not stage this candidate as a Bulb fix.** It removes a proven-wrong zeroing patch, but the correct K-3 III start/duration/stop dispatch remains unresolved and the changed non-zero path has not been exercised on Polaris. Direct-PC held-action captures are separate Layer A evidence; Polaris Layer B remains untested. Issue [#186](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/issues/186) remains open, as does libgphoto2 issue [#95](https://github.com/ian-morgan99/libgphoto2/issues/95).
