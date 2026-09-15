# Pentax stability test tooling

**Before executing any hardware scenario, read `../docs/pentax-physical-operative-runbook.md`.** The agent must choose PC vs Polaris, instruct the physical operative when a cable/body move is required, and verify enumeration after the move.

See `../docs/pentax-capture-stability-experiments.md` for experiment design and `../docs/pentax-stability-agent-handoff.md` for execution order. Copy/paste operative instructions are in `../docs/pentax-agent-operative-prompts.md`.

## Mandatory preflight

For every run establish:

```text
CAMERA=K-3 III|K-1 II
ATTACHMENT=PC|POLARIS
LAYER=A|B|C
PATH=<actual software path>
ENUMERATION_VERIFIED=yes
```

Layer A/B requires PC attachment. Layer C requires Polaris attachment. `test_pentax_scenario_routing.py` protects this routing in the scenario catalogue.

The operative's confirmation is necessary but not sufficient: the agent must observe the camera on the intended host before running the test.

The tooling deliberately separates **observation** from **camera control**:

- `pentax_stability_matrix.json` describes the planned experiments;
- `pentax_stability_scenarios.csv` routes concrete scenarios to PC/Polaris and A/B/C;
- `pentax_attachment_state.example.json` is the pre-run attachment-state contract;
- `../tools/pentax_stability_trace.py` writes durable JSONL events;
- `../tools/analyse_pentax_stability_trace.py` groups runs by the first explicitly marked abnormal event;
- `test_pentax_stability_trace.py` protects trace/matrix invariants;
- `test_pentax_scenario_routing.py` protects physical-host/layer invariants.

Example instrumentation call:

```sh
python3 tools/pentax_stability_trace.py \
  --out artifacts/pentax-E4.jsonl \
  --experiment E4 \
  --run-id E4-001 \
  --event capture_start \
  --phase requested \
  --command 264 \
  --details-json '{"camera":"K-3 III","attachment":"PC","layer":"A","path":"direct libgphoto2/gphoto2","shutter_seconds":30,"format":"dng+jpeg"}'
```

When the first divergence is observed, emit it explicitly:

```sh
python3 tools/pentax_stability_trace.py \
  --out artifacts/pentax-E4.jsonl \
  --experiment E4 \
  --run-id E4-001 \
  --event first_abnormal \
  --phase reconcile \
  --command 264 \
  --candidate-count 1 \
  --details-json '{"fingerprint":"candidate-remains-after-host-completion"}'
```

Then summarise one or more traces:

```sh
python3 tools/analyse_pentax_stability_trace.py artifacts/*.jsonl
```

The scripts are scaffolding, not a replacement for source-level instrumentation in pgphoto/libgphoto2. Prefer direct structured logging at the real state transitions once their source locations are identified.
