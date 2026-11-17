---
name: polaris-release-artifact-auditor
description: Verify actual published bytes, all mandatory companion packages, archive roots, modes, manifests, licences, hashes, index coverage, dependencies, disk constraints and downloadability. Run in pipeline against PrivateResearch remote listing, not just local staging. Use existing verify-published-astro-candidate.py as a foundation; implement #292/#350, no duplicate verifier with different policy.
---

# Polaris release artifact auditor — HARD RULE

> **HARD RULE.** Verification runs against the **PrivateResearch remote listing**,
> not against local staging. A file that exists on disk but was never uploaded is
> not published. A zip that exists locally but has different bytes on the remote
> is not the artifact a user receives.

## What is verified

| Check | Source of truth | Failure mode |
|-------|----------------|--------------|
| FwPkt.zip present and matches manifest SHA-256/MD5 | PrivateResearch remote `firmware-packets/<ver>--<id>/FwPkt.zip` | RED — user cannot flash |
| polaris-astro.zip present, non-empty, correct SHA-256 | PrivateResearch remote | RED — kit incomplete |
| polaris-wifi.zip present, non-empty, correct SHA-256 | PrivateResearch remote | RED — Wi-Fi kit missing |
| astrometry-indexes.zip present (when bundled), correct SHA-256 | PrivateResearch remote | RED — indexes absent |
| `firmwareInfo` per-file MD5s match actual bytes | Re-extracted zip, recomputed on remote | RED — on-board updater silently rejects |
| Archive root layout correct (`FwPkt/` prefix intact) | Remote zip listing | RED — watcher ignores bare zip |
| File modes (executable bits on scripts/binaries) | Remote archive listing | RED — scripts won't run |
| Licence texts present inside COPY-TO-SD-CARD-ROOT | Remote zip contents | RED — GPL/LGPL violation (#331) |
| `INSTALL.md` and `CHANGELOG.md` present and human-readable | Remote folder | RED — #356 acceptance criterion |
| Index coverage (all scales needed for the candidate) | Remote astrometry-indexes.zip | RED — solver cannot run |
| Downloadability (remote file fetchable, not truncated) | HTTP/GET of each published file | RED — user gets partial download |

## Foundation

Use `scripts/verify-published-astro-candidate.py` as the foundation. It already
verifies archives byte-for-byte against the candidate manifest. Extend it to run
against the PrivateResearch remote listing rather than only local staging.

Implements #292 (release gate: validate actual Astro v99 ZIP/tar bytes,
cross-component paths and deployability) and #350 (self-contained Astro release
packages and fail-closed publish/install gates).

## No duplicate verifier

Do not create a second verifier with different policy. If `verify-published-astro-candidate.py`
needs a new check, modify that script and update this skill to reference it.

## CI tests

CI tests must cover:
- v110 firmware-only publication
- v111 partial-kit publication
- stale source SHA
- wrong archive roots
- missing licences
- missing executable mode
- stale reused component
- missing docs
- wrong index
- upload interrupted
- GH001 size limit (100 MB)
- low clone disk

Each must produce RED. Positive full and kit-only tests must produce GREEN.

## Related skills

- `polaris-release-orchestrator` — drives the publish phase this auditor verifies.
- `polaris-release-documentation` — generates the INSTALL.md/CHANGELOG.md this auditor checks.
- `polaris-release-reconciliation` — audits version-by-version publication records.
- `fwpkt-private-upload` — uploads the zip this auditor verifies.