# Pentax stability test tooling

See `../docs/pentax-capture-stability-experiments.md` for the experiment design and `../docs/pentax-stability-agent-handoff.md` for execution order.

The initial tooling deliberately separates **observation** from **camera control**:

- `pentax_stability_matrix.json` describes the planned experiments;
- `../tools/pentax_stability_trace.py` writes durable JSONL events;
- `../tools/analyse_pentax_stability_trace.py` groups runs by the first explicitly marked abnormal event;
- `test_pentax_stability_trace.py` protects the trace/matrix invariants.

Example instrumentation call:

```sh
python3 tools/pentax_stability_trace.py \
  --out artifacts/pentax-E4.jsonl \
  --experiment E4 \
  --run-id E4-001 \
  --event capture_start \
  --phase requested \
  --command 264 \
  --details-json '{"shutter_seconds":30,"format":"dng+jpeg"}'
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
