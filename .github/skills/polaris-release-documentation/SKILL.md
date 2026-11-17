---
name: polaris-release-documentation
description: Generate mandatory INSTALL.md, CHANGELOG.md, README, compatibility matrix, recovery/rollback and install verification from exact manifests and commit diffs. Reject placeholders, stale versions, invalid commands and inaccurate test claims. Distinguish full firmware from kit-only installation. Human-readable plain English first.
---

# Polaris release documentation — HARD RULE

> **HARD RULE.** Every published candidate must have human-readable `INSTALL.md`
> and `CHANGELOG.md` in its PrivateResearch folder. Placeholders, stale versions,
> invalid commands, and inaccurate test claims are rejected. Full firmware and
> kit-only installation are distinguished explicitly.

## What is generated

| Document | Source | When required |
|----------|--------|---------------|
| `INSTALL.md` | Exact manifests + commit diffs + install route | Every candidate (full firmware and kit-only) |
| `CHANGELOG.md` | Commit diffs since previous baseline | Every candidate |
| `README.md` | Candidate identity + install routes + provenance | Every candidate |
| Compatibility matrix | Supported camera models + firmware versions | Full firmware candidates |
| Recovery/rollback | `release-fwpkt.sh` phases + install-astro-kit | Every candidate |
| Install verification | `verify-installed-build.sh` checks | Every candidate |

## Generation source

Documents are generated from exact manifests and commit diffs, not hand-written:
- `scripts/create-release-change-manifest.py` produces `release-change-manifest.json`
- `scripts/create-astro-candidate-manifest.py` produces `astro-candidate-manifest.json`
- `RELEASE-IDENTITY.md` records source SHAs, version binding, and commit history

## Distinguish release types

| Type | What it contains | Install route |
|------|-----------------|---------------|
| Full firmware | FwPkt.zip + all camera/gimbal components | `release-fwpkt.sh` (flashes appfs) |
| Astro kit-only | polaris-astro.zip + polaris-wifi.zip (+ indexes) | `install-astro-kit.sh` (stages to SD) |
| Diagnostics | Diagnostic-only build, not for device install | Documented as not-installable |

Kit-only installation must **not** be confused with full firmware. A kit-only
candidate's `INSTALL.md` must say "Astro kit only — does not flash firmware."

## Reject criteria

A document is rejected if it:
- Contains a placeholder (TBD, TODO, XXX, "to be filled")
- References a stale version or commit
- Contains an invalid command (command doesn't exist in the repo)
- Makes an inaccurate test claim (test count doesn't match actual gate output)
- Omits the install route for its release type

## Related skills

- `polaris-release-orchestrator` — requires DOCS_GENERATED phase before PRIVATE_PUBLISHED.
- `polaris-release-artifact-auditor` — verifies INSTALL.md/CHANGELOG.md are present on remote.
- `polaris-release-reconciliation` — audits documentation completeness across versions.
- `fwpkt-private-upload` — publishes README.md alongside the zip.