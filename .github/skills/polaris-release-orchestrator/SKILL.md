---
name: polaris-release-orchestrator
description: One front door for every build type. Explicit phase state machine BUILT → ARCHIVES_VERIFIED → DOCS_GENERATED → PRIVATE_PUBLISHED → REMOTE_VERIFIED; distinguish DEVICE_INSTALLED and HARDWARE_QUALIFIED. Delegate to scripts, do not substitute prose. Include stop/resume/retry, canonical command, candidate identity and machine-readable receipts. Make build success distinct from release success. Incorporates #356.
---

# Polaris release orchestrator — HARD RULE

> **HARD RULE.** Every release candidate passes through exactly one executable
> lifecycle, driven by scripts — never by prose, never by ad-hoc `ssh`/`scp`/`cp`
> against a device. Build success (`BUILT`) is **not** release success. A
> candidate is not released until it reaches `REMOTE_VERIFIED` on PrivateResearch
> with complete artifacts, `INSTALL.md`, and `CHANGELOG.md`.

## Phase state machine

| Phase | Meaning | Script that performs it | Exit condition |
|-------|---------|------------------------|----------------|
| `BUILT` | Candidate built, artifacts present, offline gate green | `scripts/build-astro.sh` / `scripts/release/build-and-install.sh` | `out/<candidate>/` complete |
| `ARCHIVES_VERIFIED` | All archives verified byte-for-byte against manifest | `scripts/verify-published-astro-candidate.py` | Remote hashes match local |
| `DOCS_GENERATED` | `INSTALL.md`, `CHANGELOG.md`, README generated from manifests | **NOT YET IMPLEMENTED** — no script emits these | Human-readable docs present |
| `PRIVATE_PUBLISHED` | All artifacts uploaded to PrivateResearch | `scripts/publish-astro-candidate.sh` | Remote listing shows all files |
| `REMOTE_VERIFIED` | Independent verifier proves remote entry is complete | `polaris-release-artifact-auditor` skill | Exact remote hashes, layout, docs |
| `DEVICE_INSTALLED` | Flashed to device via `fwpkt-update-flow` | `scripts/release/release-fwpkt.sh` | `build_id` + uptime reset + hashes |
| `HARDWARE_QUALIFIED` | Physical camera matrix passed | `scripts/canary-probe.py` / `--two-shot` | Live capture evidence |

## Canonical command

```sh
# 1. Build (BUILT)
./scripts/build-astro.sh --version N --pin FULL_DRIVER_SHA --slug NAME \
  --summary docs/release-change-summary-vN-astro.json

# 2. Verify archives (ARCHIVES_VERIFIED)
python3 scripts/verify-published-astro-candidate.py out/<candidate>

# 3. Generate docs (DOCS_GENERATED)
# NOT YET IMPLEMENTED. scripts/create-release-change-manifest.py writes
# release-change-manifest.json and RELEASE-IDENTITY.md only; no script in the repo
# emits INSTALL.md or CHANGELOG.md. Until a generator exists this phase is done by
# hand -- do not mark DOCS_GENERATED complete on the strength of the command below
# succeeding, because it produces neither document.
python3 scripts/create-release-change-manifest.py out/<candidate>

# 4. Publish to PrivateResearch (PRIVATE_PUBLISHED)
./scripts/publish-astro-candidate.sh --build out/<candidate>

# 5. Verify remote (REMOTE_VERIFIED)
# Run polaris-release-artifact-auditor against the PrivateResearch remote listing
```

## Stop/resume/retry

- A failed network/auth/size/disk upload is **recoverable state** — persist it,
  do not report a false release success.
- Resume from the last completed phase; never re-run an earlier phase that
  already produced immutable bytes.
- Published bytes are **immutable** — never overwrite an existing folder's zip.
  A new build gets a new registry id.

## Build success ≠ release success

- `scripts/build-astro.sh:422-430` prints `BUILD SUCCEEDED` and `Nothing was
  ... uploaded` — that is `BUILT` only, not released.
- `scripts/build-astro-candidate.sh:630-635` finishes `candidate complete
  (build-only)` and explicitly `No ... upload was performed` — that is `BUILT`
  only, not released.
- A candidate that stops at `BUILT` is **not published** and must not be
  treated as a release.

## Incorporates #356

Mandatory automatic PrivateResearch publication for every built version, with
complete artifacts, INSTALL, and CHANGELOG. No supported build route can report
`release complete` before full PrivateResearch remote verification.

## Delegation rule

This skill delegates to scripts. It does not substitute prose for script
execution. If a script is missing for an operation, write it, add it to
`docs/RELEASE-ENTRYPOINTS.md`, and add a test in
`tests/test_release_entrypoints.py`.

## Receipts

Every phase produces a machine-readable receipt:
- `out/<candidate>/install-receipt.txt` (install status)
- `out/<candidate>/RELEASE-IDENTITY.md` (source SHAs, version binding)
- `out/<candidate>/astro-candidate-manifest.json` (candidate identity)
- `docs/FWPKT-PROVENANCE-CONTRACT.md` (registry row for published zip)

## Related skills

- `polaris-release-artifact-auditor` — verifies actual published bytes on the
  PrivateResearch remote.
- `polaris-release-documentation` — generates mandatory INSTALL.md and CHANGELOG.md.
- `polaris-release-reconciliation` — audits built candidates vs PrivateResearch index.
- `polaris-release` — legacy; now delegates to this orchestrator.
- `fwpkt-private-upload` — legacy; now delegates to this orchestrator's publish phase.
- `fwpkt-update-flow` — device installation only (`DEVICE_INSTALLED`), not publication.
- `polaris-debugging` and camera qualification — separate, not part of this lifecycle.