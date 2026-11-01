# Version 91 testing guide

Prepared 2026-11-01. This is a testing plan, not a qualification certificate
or permission to install firmware. No hardware was operated to write it.

- [Instructions for Camera Only testing](Instructions%20for%20Camera%20Only%20testing/README.md)
- [Instructions for Astro Mode Testing and Roadmap](Instructions%20for%20Astro%20Mode%20Testing%20and%20Roadmap/README.md)

## Exactly which release?

This guide concerns **6.0.0.54.91**, candidate
`astro-v1-camera-baseline-20261101`, published in
[PrivateResearch](https://github.com/ian-morgan99/PrivateResearch/tree/main/firmware-packets/6.0.0.54.91--astro-v1-camera-baseline-20261101).

| Input | Recorded identity |
|---|---|
| Patcher / Astro commit | `6825029c9803c243dcfbe721e4cbea3b531da8dd` |
| Shared camera baseline | `8c015c0a73c8affea8fa723badcceb4070ef81b4` |
| libgphoto2 | `051d224dbd33fda67ff65ce73a6d6bbd9c9a3aff` |
| FwPkt.zip SHA-256 | `7c11f9a033b2372f1215aca89e3f6ac46544047f26802fe94a68b77217be01d2` |
| Astro bundle SHA-256 | `40fe08e7c87e24d5e30fb42660afc917d4ad0df1d227617ac8bfc62d6b0b9a13` |

The published README, `astro-candidate-manifest.json`,
`build-source-provenance.txt`, `install-manifest.json` and `install-status.txt`
are the release-specific evidence. Verify actual downloaded bytes against
them. A display version alone does not establish identity.

The publication records **not installed; physical qualification not performed**.
It requires camera-baseline acceptance or an explicit #251 waiver and a
supervised test window before installation. Recheck current issue status;
do not assume a later source fix is present in these immutable v91 bytes.

`FwPkt.zip` and `astro-bundle.tar.gz` are separate artifacts. Installing the
firmware does not by itself install the additional Astro SD-card content.
Camera-only testing must leave any existing Astro automation disabled too.

## Common rules

- One operator owns Polaris; one client owns the camera session. Do not run
  BenroConnect, OpenPolaris and a diagnostic camera client simultaneously.
- Arrange a recoverable, provenance-known previous firmware before testing.
  Recovery also uses the supported installer; do not copy binaries into `/app`.
- Installation is an operator/agent-assisted task using the current
  [firmware install process](../FIRMWARE-INSTALL-PROCESS.md) and its documented
  Bluetooth wake, verification and reboot steps. Do not improvise an updater.
- Stop at the first unexpected capture, unclosed exposure, crash, abnormal
  camera noise or unusual camera/battery heating. Do not repeatedly retry.
  Let the supervising operator recover safely; preserve logs first if safe.
- Record PASS, FAIL, BLOCKED, SKIPPED or NOT TESTED for each case. A successful
  command, shutter sound, thumbnail or emulator run alone is not a full pass.
- Keep model, body firmware, lens, app/version, settings, original values,
  timestamps, file identities and observed durations with every result.
- Collect Mlog and Clog for the same time interval through the existing
  documented diagnostic process. Do not clear logs to make a run look clean.
- Camera battery and gimbal battery are different measurements. Protocol 778
  is gimbal battery, not camera temperature or camera battery evidence.

Use the result template in [TEST-RECORD.md](TEST-RECORD.md). Never mark tests
complete merely because this guide exists.

## Documentation ownership

These new documents were added at the user's explicit request. They do not
modify the dirty camera/release implementation in the Astro checkout. Transfer
them through the normal reviewed documentation commit/handoff; they are not
evidence that this checkout is a clean release source. Publishing these guides
alongside the packet remains a separate action until recorded as done.
