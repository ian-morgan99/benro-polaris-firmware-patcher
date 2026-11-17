---
name: polaris-release-reconciliation
description: Audit built candidates vs PrivateResearch index; detect missing/incomplete/mislabelled versions, recover/retry safely, preserve immutable published binaries, produce version-by-version exception ledger. Backfill v110/v111 and audit older candidates.
---

# Polaris release reconciliation — HARD RULE

> **HARD RULE.** Published bytes are immutable. A reconciliation never modifies,
> overwrites, or deletes an existing published artifact. It detects exceptions
> and produces a ledger; recovery creates new rows with new ids, never replaces.

## What is audited

| Audit | Compared against | Exception recorded |
|-------|-----------------|-------------------|
| Built candidates vs PrivateResearch index | `docs/FWPKT-PROVENANCE-CONTRACT.md` registry | Missing row, hash mismatch, mislabelled version |
| PrivateResearch index vs remote listing | `ian-morgan99/PrivateResearch/firmware-packets/` | Folder present locally but absent remotely, or vice versa |
| Version uniqueness | Display version + registry id | Duplicate version with different id (#169 class) |
| Companion package completeness | FwPkt + astro + wifi + indexes + docs | Missing companion package for a kit candidate |
| Docs completeness | INSTALL.md + CHANGELOG.md + README.md | Missing human-readable docs |

## Backfill targets

- **v110** (`6.0.0.54.109`): firmware ZIP and docs present, but no Astro/Wi-Fi
  companion ZIPs; lacks dedicated INSTALL/CHANGELOG.
- **v111** (`astro-v111--webui-opens-20261117`): kit-only, lacks dedicated
  INSTALL/CHANGELOG.
- All older candidates: audit publication records, link to #350/#356.

## Recovery/retry

- A missing or incomplete publication is recovered by **re-publishing** with a
  new registry id — never by overwriting existing bytes.
- An interrupted upload is resumed from the last completed phase (see
  `polaris-release-orchestrator`).
- A mislabelled version gets a new row; the old row is annotated as superseded.

## Exception ledger

Produces a version-by-version exception ledger recording:
- Candidate id, display version, patcher SHA, libgphoto2 SHA
- Which phases completed (BUILT, ARCHIVES_VERIFIED, DOCS_GENERATED, PRIVATE_PUBLISHED, REMOTE_VERIFIED)
- Which phases are missing or failed
- Whether the candidate is installable or NOT_HARDWARE_QUALIFIED

## Related skills

- `polaris-release-orchestrator` — defines the phases this reconciliation audits.
- `polaris-release-artifact-auditor` — verifies individual remote entries.
- `polaris-release-documentation` — generates docs that reconciliation checks for completeness.
- `fwpkt-private-upload` — uploads artifacts that reconciliation tracks.