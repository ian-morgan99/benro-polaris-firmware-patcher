---
name: polaris-release-documentation
description: Write and verify the install, change, recovery and compatibility records for an exact Polaris firmware or Astro kit candidate.
---

# Write Polaris release records

Use the exact manifests, source commits, component diffs and recorded tests. `scripts/create-release-change-manifest.py` writes release-change-manifest.json and RELEASE-IDENTITY.md. The candidate builders provide its arguments. `scripts/create-astro-candidate-manifest.py` writes the Astro candidate manifest. Review those machine records, then write or review these reader-facing files before release handoff:

- **INSTALL.md** names the release type, exact downloads and digests, target and prerequisites, copy or install steps, verification and rollback. Include required indexes and Wi-Fi recovery where applicable.
- **CHANGELOG.md** names the previous reference, changes and affected components, tests and skips, and open limitations and issues.
- **README.md** identifies the artifact set and links the instructions, changelog, manifests and relevant evidence.

For a full firmware install use [the firmware install process](../../../docs/FIRMWARE-INSTALL-PROCESS.md). For kit-only delivery, name the compatible firmware and use the kit section of [the Astro release runbook](../../../docs/ASTRO-CANDIDATE-RELEASE.md). Tell the reader whether any step writes the SD card or reboots the mount. Check each command against the current script and its argument parsing.

List the tested camera model, firmware, attachment, mode, format and client for each physical claim. Show installed and loaded identity separately from the build result. When tests are pending, give the exact gate still due. Attach or link the previous known-good recovery artifact and instructions.

Use [the release workflow](../polaris-release-orchestrator/SKILL.md) for milestone records and [the artifact audit](../polaris-release-artifact-auditor/SKILL.md) to check the published copies.
