# Pentax stability plan v1 — 2026-09-15

Initial causal stability package.

Key changes from earlier recovery-centric thinking:

- treats stale session as potentially downstream rather than universal root cause;
- adds hardware characterisation of Pentax NR/Pixel Shift/Bulb timing and outputs;
- separates physical exposure count from transfer candidate count;
- adds timeout-boundary, concurrency, preview-race, back-to-back, candidate, history, soak and fault-injection experiments;
- excludes OpenPolaris from first-cause isolation but defines its later E2E role;
- adds first-divergence structured trace/fingerprint scaffolding;
- adds falsifiable hypotheses, objective metrics and evidence levels;
- defines deterministic command ownership, recovery and data-safety contracts.
