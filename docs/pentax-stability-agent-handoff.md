# Agent handoff: causal Pentax stability campaign

Read `docs/pentax-capture-stability-experiments.md` before changing camera lifecycle/recovery code.

## Objective

Use the physically connected Pentax/Polaris environment to discover repeatable **initiating failure recipes**. Do not begin by making reset/retry more aggressive.

## First implementation task

Integrate or adapt `tools/pentax_stability_trace.py` around the existing Polaris-side pgphoto/libgphoto2 test path. The recorder is intentionally observation-only; do not replace existing deterministic camera control with Python wrappers unless required.

Populate `tests/pentax_stability_matrix.json` with exact commands/settings available on the current firmware and execute in priority order.

Start with:

1. E4/E5 consecutive DNG+JPEG candidate lifecycle;
2. E1 95/99/100/101/105 second boundary sweep;
3. E2/E3 one-command concurrency and preview races;
4. E6 120/300 second completion/readout boundary;
5. E12 history dependence;
6. E11 soak.

Do not run destructive E7-E9 until normal lifecycle traces are understood.

## Required discipline

- Keep OpenPolaris out of the first diagnostic path.
- Keep preview OFF for the initial baseline.
- Change one variable at a time.
- A/B/A where practical.
- Repeat failures and report failures/runs.
- Mark the first divergence as `first_abnormal`; do not label a later stale session as root cause without evidence.
- Preserve paired Mlog/Clog and exact patcher/libgphoto2 SHAs.
- Never delete/purge an unknown DNG candidate merely to clear state.
- Never classify a multi-minute exposure as dead solely because elapsed time crossed a fixed timeout.
- Do not allow LLM/heuristic runtime decisions to control session ownership or candidate reconciliation.

## Expected deliverables

For each reproducible failure family, add/update a focused GitHub issue containing:

- minimal reproduction;
- exact first abnormal event;
- trace excerpt and raw trace artifact/location;
- Mlog/Clog correlation;
- layer attribution;
- source path/function implicated;
- deterministic proposed fix;
- regression test;
- evidence distinguishing cause from aftermath.

Cross-reference #82 as the field-stability umbrella.

## Stop conditions

If a test risks repeated camera lock/power-cycle, DNG loss, filesystem corruption, or uncontrolled process restart loops, stop that branch and document the evidence obtained. Prefer observability over destructive repetition.
