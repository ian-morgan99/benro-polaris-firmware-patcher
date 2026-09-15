# Pentax stability investigation index

Start here for the current K-3 III / Pentax stability investigation.

## Mandatory execution entry point

- [`pentax-physical-operative-runbook.md`](pentax-physical-operative-runbook.md) — **read first when executing hardware tests**. Defines Layer A (PC direct), Layer B (PC Benro-compatible harness), Layer C (real Polaris), and the mandatory agent/physical-operative handshake for moving the camera between PC and Polaris.

The testing agent is responsible for deciding where each test runs, explicitly instructing the physical operative when to move the camera, and verifying the new host actually enumerates the expected camera before continuing.

## Design and experiments

- [`pentax-capture-stability-experiments.md`](pentax-capture-stability-experiments.md) — complete causal experiment programme, Pentax mode-aware lifecycle and recovery contract.
- [`pentax-stability-root-cause-map.md`](pentax-stability-root-cause-map.md) — candidate initiating causes vs common aftermath symptoms.
- [`pentax-stability-agent-handoff.md`](pentax-stability-agent-handoff.md) — agent execution instructions and A/B/C progression.
- [`pentax-k1ii-second-pass.md`](pentax-k1ii-second-pass.md) — K-1 II second-pass strategy.
- [`pentax-mode-aware-liveness.md`](pentax-mode-aware-liveness.md) — long exposure, NR, Pixel Shift and liveness semantics.
- [`pentax-capture-stability-experiments.schema.json`](pentax-capture-stability-experiments.schema.json) — failure fingerprint schema.

## Test scaffolding

- [`../tests/pentax_stability_matrix.json`](../tests/pentax_stability_matrix.json) — initial machine-readable experiment matrix.
- [`../tests/pentax_stability_scenarios.csv`](../tests/pentax_stability_scenarios.csv) — concrete K-3 III pass-1 and K-1 II pass-2 scenarios.
- [`../tests/pentax_safe_command_matrix.csv`](../tests/pentax_safe_command_matrix.csv) — hardware-characterised command/phase safety matrix.
- [`../tools/pentax_stability_trace.py`](../tools/pentax_stability_trace.py) — observation-only JSONL event recorder.
- [`../tools/analyse_pentax_stability_trace.py`](../tools/analyse_pentax_stability_trace.py) — first-divergence/failure fingerprint summariser.
- [`../tests/test_pentax_stability_trace.py`](../tests/test_pentax_stability_trace.py) — trace/matrix invariant tests.
- [`../tests/README-pentax-stability.md`](../tests/README-pentax-stability.md) — quick start.

## Issue tracking

- #82 is the external field-stability umbrella and evidence coordination point.
- Keep focused source defects in their own issues and cross-reference #82.

## Investigation principle

> Find and fix the first incorrect state transition. Do not mistake a stale session or successful recovery for an explanation of why the healthy session failed.

Runtime ownership, deadlines, candidate reconciliation and recovery must remain deterministic. LLMs/agents may analyse evidence and propose patches, but must not become part of camera-session runtime control.
