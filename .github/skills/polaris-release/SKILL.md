---
name: polaris-release
description: Legacy release skill — now a concise routing guide that delegates to polaris-release-orchestrator. Does not duplicate the release lifecycle; references the authoritative orchestrator skill instead.
---

# Polaris release — routing guide (delegates to polaris-release-orchestrator)

This skill is a **concise routing guide**. It does not duplicate the release
lifecycle. The authoritative lifecycle is in
`.github/skills/polaris-release-orchestrator/SKILL.md` (phase state machine
`BUILT → ARCHIVES_VERIFIED → DOCS_GENERATED → PRIVATE_PUBLISHED → REMOTE_VERIFIED`,
plus `DEVICE_INSTALLED` and `HARDWARE_QUALIFIED`).

## When to use

Use this skill only to locate the correct entrypoint for a release operation.
Every operation is performed by a script indexed in `docs/RELEASE-ENTRYPOINTS.md`.
Do not hand-roll a Docker build, copy runtime binaries into `/app`, or publish a
ZIP without provenance.

## Canonical entrypoints

| Operation | Command | Phase reached |
|-----------|---------|---------------|
| Prove build host works | `./scripts/build-doctor.sh` | Pre-flight |
| Build an Astro candidate | `./scripts/build-astro.sh --version N --pin FULL_DRIVER_SHA --slug NAME --summary ...` | `BUILT` |
| Build a camera-only candidate | `./scripts/release/build-and-install.sh --install` | `BUILT` (+ optional install) |
| Verify archives | `python3 scripts/verify-published-astro-candidate.py out/<candidate>` | `ARCHIVES_VERIFIED` |
| Generate docs | `python3 scripts/create-release-change-manifest.py out/<candidate>` | `DOCS_GENERATED` |
| Publish to PrivateResearch | `./scripts/publish-astro-candidate.sh --build out/<candidate>` | `PRIVATE_PUBLISHED` |
| Verify remote entry | `polaris-release-artifact-auditor` skill | `REMOTE_VERIFIED` |
| Flash to device | `scripts/release/release-fwpkt.sh out/<candidate>` | `DEVICE_INSTALLED` |
| Physical camera matrix | `scripts/canary-probe.py` / `--two-shot` | `HARDWARE_QUALIFIED` |

## Build success ≠ release success

`scripts/build-astro.sh` prints `BUILD SUCCEEDED` and `Nothing was ... uploaded`.
`scripts/build-astro-candidate.sh` finishes `candidate complete (build-only)`
and explicitly `No ... upload was performed`. Both reach `BUILT` only — **not**
released. A candidate is not released until `REMOTE_VERIFIED` on PrivateResearch
with complete artifacts, `INSTALL.md`, and `CHANGELOG.md`.

## What this skill does NOT do

- Does **not** define a competing release lifecycle. The orchestrator skill is
  authoritative.
- Does **not** treat "upload FwPkt only" as a sufficient release definition.
  Publication requires FwPkt + all companion archives + docs + remote
  verification.
- Does **not** handle device installation — that is `fwpkt-update-flow`
  (`DEVICE_INSTALLED` only).
- Does **not** handle camera qualification — that is `pentax-hardware-stability`
  and the canary gates (`HARDWARE_QUALIFIED` only).

## Required handoff

Record and hand over all of:

* patcher `main` SHA;
* libgphoto2 `main` SHA;
* candidate/build ID;
* ZIP MD5 and SHA-256;
* appfs MD5;
* PrivateResearch commit and path;
* gate result and any skipped prerequisites.

## Review rule

Before physical testing, an independent reviewer must inspect the two source
SHAs, the gate transcript, the provenance row, and the exact PrivateResearch
artifact hashes. A historical or diagnostic build must have a distinct ID and
must not overwrite an existing artifact.
