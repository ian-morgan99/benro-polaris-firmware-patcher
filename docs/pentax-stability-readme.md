# Pentax stability package

Entry point: [`pentax-stability-index.md`](pentax-stability-index.md).

This package captures the September 2026 causal stability design: mode-aware Pentax liveness, candidate lifecycle, concurrency, process/USB separation, adversarial hardware experiments, first-divergence tracing, deterministic recovery and eventual OpenPolaris E2E requalification.

The code under `tools/` and data under `tests/` are initial scaffolding for agents with access to the physical Polaris + Pentax environment. They should be adapted to existing repo conventions rather than duplicated if equivalent infrastructure already exists.
