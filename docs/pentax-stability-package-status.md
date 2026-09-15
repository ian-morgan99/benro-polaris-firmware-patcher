# Pentax stability package status

**Plan version:** v1, 2026-09-15.

Implemented in repository:

- causal experiment design and staged execution order;
- Pentax mode-aware liveness/Pixel Shift/NR semantics;
- root-cause map and evidence standards;
- deterministic command/recovery/data-safety contracts;
- static audit templates for timeouts, command entry points and session-state survival;
- machine-readable scenario/hypothesis/status/metric/fingerprint registers;
- JSONL trace recorder + analyser scaffolding;
- unit/consistency tests for core test-plan invariants;
- agent handoff/reporting/review instructions;
- OpenPolaris reintroduction and K-1 II cross-validation plan.

Not yet claimed complete:

- source-level trace integration into pgphoto/libgphoto2;
- completed static audit tables;
- physical K-3 III experiment results;
- behavioural fixes arising from those results.

Those are deliberately left as evidence-driven next work rather than being guessed into this documentation commit series.
