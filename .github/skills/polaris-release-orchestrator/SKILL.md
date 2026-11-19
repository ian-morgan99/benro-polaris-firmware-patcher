---
name: polaris-release-orchestrator
description: Plan Polaris builds and track the evidence for archives, documentation, private publication, device installation and hardware qualification.
---

# Polaris release workflow

Read [release entry points](../../../docs/RELEASE-ENTRYPOINTS.md), [version state](../../../docs/RELEASE-VERSION-STATE.md) and the [active WBS](../../../docs/ISSUE-WBS-2026-11-14.md). Use these instructions from a checkout with any terminal or GitHub client. Record the intended release type, exact clean source pair, stock hash, previous qualified reference, version and declared changes before choosing a command.

| Intent | Entry point | Side effects |
|---|---|---|
| Local Astro candidate | `scripts/build-astro.sh --version N --summary FILE` | Builds and gates archives and records the version claim. |
| Camera firmware candidate with private packet upload | `scripts/build-release-candidate.sh ID STOCK LIB_CHECKOUT auto auto --change-summary FILE` | Builds, gates, records the version claim and publishes the camera packet. Supply the exact clean driver checkout. |
| Publish an Astro candidate | `scripts/publish-astro-candidate.sh --build out/ID` | Commits and pushes to PrivateResearch. |
| Stage firmware | `scripts/release/release-fwpkt.sh out/ID --skip-trigger` | Writes the extracted tree to the SD card and verifies it. |
| Install firmware | `scripts/release/release-fwpkt.sh out/ID` | Stages, verifies, reboots and confirms installed files. |
| Install a matched kit | [Firmware vs kit instructions](../polaris-release-documentation/SKILL.md) | Updates the SD kit using its firmware compatibility contract. |

The convenience wrapper `scripts/release/build-and-install.sh` uses the camera build and publication path. Its `--install` option also wakes, flashes and reboots the device. Use the explicit-checkout builder when testing an exact driver commit.

Record each milestone with its own evidence:

1. **BUILT** — exact source and artifact manifests, release gate transcript, explicit skips.
2. **ARCHIVES_VERIFIED** — inspect required files for the release type and perform the local checks in the [artifact auditor](../polaris-release-artifact-auditor/SKILL.md). Exit zero from the local verifier alone is insufficient.
3. **DOCS_GENERATED** — use the [documentation procedure](../polaris-release-documentation/SKILL.md). The change manifest utility writes JSON and RELEASE-IDENTITY.md. A general INSTALL/CHANGELOG generator is **NOT YET IMPLEMENTED**.
4. **PRIVATE_PUBLISHED** — record the PrivateResearch commit and immutable artifact paths. The camera packet builder uploads during its run. Complete and check the companion records before advertising the candidate.
5. **REMOTE_VERIFIED** — fetch the exact published files and compare them with the reviewed artifacts per the [artifact auditor](../polaris-release-artifact-auditor/SKILL.md).
6. **DEVICE_INSTALLED** — record card verification and reboot receipt, app version, build ID and installed hashes. Run the [installation skill](../fwpkt-update-flow/SKILL.md) on the identified target.
7. **HARDWARE_QUALIFIED** — bind each result to the installed and loaded runtime and the tested body, client, mode and format. Use the [Pentax stability](../pentax-hardware-stability/SKILL.md) and [repeated capture](../astro-multishot-qualification/SKILL.md) procedures. `tests/run_prerelease_gate.sh --canary --two-shot` is a live canary path when its prerequisites are met. Report its tested coverage and skips.

For a retry, confirm whether the previous command already claimed a version, published bytes or changed the device. Reuse verified intermediate output and keep prior artifact bytes immutable. Resume from the first missing milestone.
