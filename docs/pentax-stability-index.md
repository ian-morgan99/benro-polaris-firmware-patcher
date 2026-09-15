# Pentax stability investigation index

Start here for the current K-3 III / Pentax stability investigation.

## Design and experiments

- [`pentax-capture-stability-experiments.md`](pentax-capture-stability-experiments.md) — complete causal experiment programme, Pentax mode-aware lifecycle and recovery contract.
- [`pentax-stability-root-cause-map.md`](pentax-stability-root-cause-map.md) — candidate initiating causes vs common aftermath symptoms.
- [`pentax-stability-agent-handoff.md`](pentax-stability-agent-handoff.md) — execution instructions for an agent with physical Polaris/camera access.
- [`pentax-capture-stability-experiments.schema.json`](pentax-capture-stability-experiments.schema.json) — failure fingerprint schema.

## Test scaffolding

- [`../tests/pentax_stability_matrix.json`](../tests/pentax_stability_matrix.json) — initial machine-readable experiment matrix.
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
