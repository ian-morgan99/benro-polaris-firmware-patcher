---
name: polaris-regression-preservation-review
description: For each PR affecting camera, firmware, Astro, Wi-Fi or installation, require changed-component manifest, stock/previous-version feature diff, negative regression tests and explicit unverified hardware matrix; prevent accidental removal of prior functionality. Existing gates and #293 remain authoritative.
---

# Polaris regression preservation review — HARD RULE

> **HARD RULE.** No PR touching camera, firmware, Astro, Wi-Fi, or installation
> may remove previously working functionality without an explicit changed-component
> manifest, a stock/previous-version feature diff, negative regression tests, and
> an explicit unverified hardware matrix.

## What every PR must include

| Artifact | Purpose |
|----------|---------|
| Changed-component manifest | Lists every component the PR touches (camlib, iolib, loader, wrapper, WebUI, installer, gate script, etc.) |
| Stock/previous-version feature diff | Compares current behavior against the last known-good release for each touched component |
| Negative regression tests | Tests that would have caught the regression if it were reintroduced |
| Explicit unverified hardware matrix | Lists which camera models/modes are NOT verified by this PR, so nothing is assumed qualified |

## What is prevented

- Accidental removal of prior functionality (e.g., a WebUI change that breaks
  shutter dispatch for a previously supported mode)
- Silent regression of a previously qualified camera path
- A build that passes the gate but ships different behavior than the previous
  release for the same component
- Promoting "offline GREEN" to "device qualified" without hardware evidence (#203/#216)

## Existing gates that remain authoritative

- `#293` — MASTER WBS: v99 install, diagnostics, Astro services and real Pentax/stock camera qualification
- `tests/run_prerelease_gate.sh` — the pre-release gate (fail-closed)
- `tests/run_deterministic.sh` — deterministic patch/patcher behaviour
- `container/test_*.sh` — container harness tests

## Related skills

- `polaris-release-orchestrator` — the release lifecycle this review gates.
- `polaris-release-artifact-auditor` — verifies published artifacts match what was reviewed.
- `polaris-release` — legacy release skill, now delegates to orchestrator.
- `pentax-hardware-stability` — camera-specific stability investigations (separate concern).