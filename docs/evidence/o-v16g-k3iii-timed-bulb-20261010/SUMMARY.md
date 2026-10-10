# o-v16g K-3 III timed-Bulb dispatch candidate — 2026-10-10

## Status

Built from verified stock firmware and uploaded to the private artifact repository. Offline gates passed. **Not installed or physically tested on Polaris; issue #186 remains open.** This is an install/test candidate, not a claim that Polaris Bulb now works.

The pgphoto patch uses the existing timed helper after the exact code-264 capture request reaches `capture_image_with_Burst`. For positive `bTime`, status 0, Pentax manufacturer, and K-3 Mark III model, it routes to `capture_image_with_Bulb(Status, time_ms, newFiles)`. The helper sends the `bulb=1` action, waits for the requested milliseconds, sends `bulb=0`, and follows its existing finalize/transfer path. Zero-duration capture, other models, and Monochrome keep the old path. The original `captureBulbImage` entry and indirect Nikon model-table reference are preserved; the new trampoline occupies an audited zero-filled executable LOAD tail and is protected from Stage-2 trampoline overlap.

This wiring is based on stock-binary disassembly and the direct-PC K-3 III held-action evidence. It still needs an actual Layer B test to prove that the shipped pgphoto callback reaches the PTP start/stop sequence, captures for the requested duration, publishes output, and returns idle. No firmware install or camera operation is claimed here.

## Provenance

- Candidate ID: `o-v16g-k3iii-timed-bulb-20261010`
- Display version / build ID: `6.0.0.54.65` / `6.0.0.54.65-o-v16g-k3iii-timed-bulb-20261010`
- Patcher source: [`9d0efe0abd6125ef04d38bb0789f3b50597a373f`](https://github.com/ian-morgan99/benro-polaris-firmware-patcher/commit/9d0efe0abd6125ef04d38bb0789f3b50597a373f), the exact Patcher `main` commit at build time (the clean checkout retained the feature-branch name)
- libgphoto2 source: [`2cde4485b0222b38c364f8893f487228102c2d2d`](https://github.com/ian-morgan99/libgphoto2/commit/2cde4485b0222b38c364f8893f487228102c2d2d), clean `main`
- Selected camlibs: `ptp2,pentax`; full matched libgphoto2 core/port/ptp2/usb1 stack
- Stock FwPkt: MD5 `90bdad511f556f25a2904ae9d2980102`; SHA-256 `f980fe5245a1f85b58d0c2db523402d1af72ddfff782acba99a4eadfdca54d2f`; appfs MD5 `47f2ae680be3a5f5d69aa20e20a2397b`
- Candidate FwPkt: MD5 `4ce76e1a3d4be7830713c2609989b384`; SHA-256 `abee7692bbb50d0fef9147d3cce70fb21eefba9c9f4adb4e0e43a00b6f8e4d7b`; appfs MD5 `28f597774a55aa2f49fdbc48cd099d5a`
- PrivateResearch ZIP commit: `50b4c108c5a98869b6fcd0c19c04a27dcd10cf7a`; ZIP at `firmware-packets/o-v16g-k3iii-timed-bulb-20261010/FwPkt.zip`. Its patcher-SHA/status README is commit `1050e0ac6`; ZIP bytes and hashes are unchanged.

## Validation

- libgphoto2 deterministic build suite: 16 passed; the host-specific `no-ci` DTR/CTS fixture was excluded by the release command.
- Patcher deterministic container suite: 20 passed.
- Python regression suite: 211 passed.
- Offline prerelease gate: 8 passed, 0 failed, 1 skip. The skip was the manifest check’s conventional `firmware/FwPkt.zip` lookup because the clean feature checkout used an external stock path; the release builder and private upload separately verified the actual stock input and the final zip’s six firmwareInfo hashes/sizes.
- Parameterized DISPLAY_FWVER package regression: passed.
- Final appfs audit: original polestar Bulb request branch intact; timed pgphoto dispatcher present.
- ZIP structural validation and firmwareInfo self-consistency: passed.
- Complete build/upload output: [build-release-candidate.txt](./build-release-candidate.txt).

## Required next proof

Install only through the documented FwPkt update flow after an independent review of both source SHAs, this evidence, and the exact artifact hashes. With the K-3 III attached to Polaris and Benro Connect absent, run a bounded single Bulb capture with a known requested duration. Prove from trace that code 264 yields exactly one PTP start and stop, compare elapsed exposure with the requested duration, preserve and inspect the resulting file, verify camera idle/output reconciliation, then run a Manual control capture. Any ambiguous start/stop or missing output is `OUTCOME UNKNOWN`; do not retry shutter commands. Until that Layer B evidence exists, the candidate is `built, canary pending`, not qualified. Keep the K-3 III Monochrome blocked.
