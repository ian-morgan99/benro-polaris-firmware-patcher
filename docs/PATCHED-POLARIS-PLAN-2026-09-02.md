# Patched Polaris recovery plan

## Decision

The patched application payload is not the current blocker. The full libgphoto2
mode has already been verified on the target hardware, and the build validates
both archive structure and `firmwareInfo` checksums before shipping.

The blocker is delivery: prior work mixed three different update mechanisms:

| Mechanism | Artifact | Status |
|---|---|---|
| Main Polaris/gimbal update | `FwPkt.zip` | Target mechanism; installer trigger is not yet reproduced on the live unit. |
| OMS update | `OmsPkt.zip` | Separate package and state machine. Do not use it to install this patch. |
| On-disk stage-2 test | Files below `/app/lib/stage2` | Reversible validation route, already supported by the build. |

`SP_OmsUpgradeCheckFwPkt` is misleadingly named: its resolved paths are
`/app/sd/OmsPkt.zip` and `/app/sd/OmsPkt`, so it is not evidence that it will
install `FwPkt.zip`. Likewise, the proposed `devmem`/`himm` register write has
not been demonstrated to consume the patched archive. Neither is an approved
install route.

## Immediate plan

1. Rebuild or select exactly one candidate: the default full-mode output from
   `builds/2026-08-30-padded-appfs/FwPkt.zip`. Run both validators and record
   its SHA-256 beside the physical SD card image. Do not change version strings
   or `polestar_app` merely to make the phone UI display a newer version.
2. Make a recovery SD card first with pristine stock `FwPkt.zip`; verify its
   checksum and retain it untouched. Make a second FAT-formatted card with only
   the candidate `FwPkt.zip` at its root. An on-device copy to `/app/sd` is not
   an equivalent test of the physical-card procedure.
3. Establish the baseline with the stock card using the exact official Benro
   firmware-update gesture. Capture a serial/boot log if available, or at
   minimum record lights, elapsed time, resulting files, and post-boot version.
   This is the discriminating check: if stock does not install, stop debugging
   custom firmware and fix the physical update procedure first.
4. Repeat unchanged with the patched card. Success requires more than a reboot:
   preserve evidence that the updater read `FwPkt.zip` and verify the patched
   libgphoto2 behavior after boot. If the device fails to boot normally, flash
   the prepared stock card before attempting any new experiment.
5. Only if stock succeeds but the patched archive is rejected, capture the
   complete updater log and compare its archive layout, component MD5s, sizes,
   and filenames against stock. Then inspect `SP_UpgradeCheckFw` and
   `SP_SrchGimbalNewPkt`, which are the `FwPkt` path, rather than the OMS code.

## Evidence gates

| Gate | Required evidence | Action on failure |
|---|---|---|
| Build | `verify_firmwareinfo.py` and `validate_fw_package.py` pass on the exact zip | Do not stage or flash it. |
| Physical route | Stock `FwPkt.zip` installs using the documented physical procedure | Stop; the route is not established. |
| Custom acceptance | Log or observable behavior proves the updater read the custom zip | Compare against the stock baseline; do not alter unrelated code. |
| Runtime | Patched camera workflow works after a cold boot | Publish the artifact and evidence. |
| Recovery | Stock card restores the unit | Investigate the patch offline before retrying. |

## Agent failure analysis

- **Conflated artifact families.** The OMS function's name contains `FwPkt`,
  but its strings name `OmsPkt.zip`; this led to conclusions about the wrong
  installer. Treat resolved file paths as stronger evidence than symbol names.
- **Promoted hypotheses to runbooks.** `STATE.md` and the SD runbook disagree
  about boot, Wi-Fi `810`, extraction, and hardware-register triggers. A plan
  may only declare a route usable after it installs the pristine stock package.
- **Repeated broad disassembly after a decisive test was available.** The
  physical stock-card baseline is cheaper and more informative than tracing
  speculative alternate triggers.
- **Allowed stale documents to remain authoritative.** `STATE.md` still calls
  earlier, contradicted paths "confirmed". This document supersedes its
  installer guidance until the stock-card baseline is captured.
- **Tool-loop churn obscured progress.** The ledger records high error,
  fallback, divergence, and context-pressure rates, plus repeated reviews with
  stale scan counts. Long raw tool outputs should be archived once, then cited
  by a concise decision record.

## Future modification workflow

1. State the target behavior, firmware version, and recovery method before
   modifying an image.
2. Prefer the reversible `stage2-ondisk` bundle to validate a new runtime
   modification before creating a flashable package.
3. Change one subsystem per artifact. Keep an immutable stock input, a manifest
   of modified files, source revision, command line, and output checksums.
4. Require both package validators and an extracted-image diff that explains
   every changed file.
5. Validate on hardware from a cold boot, with a stock recovery card prepared.
   Record device model, connected camera, observed behavior, and logs in
   `docs/TESTED.md`.
6. Update `STATE.md` only with dated facts, exact artifact hashes, and the next
   falsifiable experiment. Move disproved hypotheses to a short retired section
   rather than leaving them in the active TL;DR.

## Work that should not continue yet

Do not patch the `6.0.0.54` display value, emulate USB UART, invoke OMS
commands, write device registers, or add another delivery mechanism until the
stock physical-SD baseline has succeeded or failed with captured evidence.