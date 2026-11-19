---
name: polaris-release-artifact-auditor
description: Audit the exact downloaded PrivateResearch files for a Polaris firmware or Astro kit release, including completeness, archive layout and digests.
---

# Audit a Polaris release

Use the candidate's release type, exact source and version records and reviewed manifests to write down the required files and expected hashes before checking any directory.

| Type | Check for |
|---|---|
| Camera firmware | FwPkt.zip, build identity and change/install manifests, release and recovery instructions |
| Firmware plus Astro | Firmware set plus the declared Astro bundle, SD-root Astro and Wi-Fi ZIPs and declared index delivery |
| Kit only | SD-root Astro and Wi-Fi ZIPs, declared indexes or an explicit provisioned-index dependency, compatible firmware identity and kit instructions |

An explicitly external dependency needs a pinned source and a usable install check. Missing required files, stale hashes, or unpublished docs fail the audit. Optional files need an explicit reason to mark them not applicable. Check licence notices, executable modes, archive roots, package dependencies and required index coverage for the declared components.

1. Run `python3 scripts/verify-published-astro-candidate.py CANDIDATE_DIRECTORY` for local Astro archive structure. Inspect individual results. This tool is local only and permits UNKNOWN or NOT_APPLICABLE in some cases. An empty staged kit directory can return zero.
2. Fetch the exact PrivateResearch commit through an authenticated GitHub client or a dedicated clone. Record branch reachability, commit, path, file names and digests. Download the actual content and compare with the independently recorded hashes and sizes. If Git LFS is used, verify resolved payload bytes.
3. Inspect the downloaded files. Re-run the applicable structural checks and verify any firmware archive's `firmwareInfo` against its extracted members. Check that the paired kit and firmware identities match and that the published instructions use those exact files.
4. Record required files as PASS, FAIL or UNVERIFIED. Record REMOTE_VERIFIED only when every applicable remote check passes.

Use the existing verifier for future strict completeness work under #292/#350. Preserve negative fixtures for missing or empty archives, wrong root, bad digest, missing executable mode, missing licences, stale component, missing docs, and interrupted or truncated download. A release of each supported type also needs a positive fixture. See the [release workflow](../polaris-release-orchestrator/SKILL.md).
