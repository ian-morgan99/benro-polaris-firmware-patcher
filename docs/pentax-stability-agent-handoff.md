# Agent handoff: causal Pentax stability campaign

Read these before changing camera lifecycle/recovery code:

1. `docs/pentax-physical-operative-runbook.md` — **mandatory physical attachment and A/B/C execution protocol**;
2. `docs/pentax-capture-stability-experiments.md` — experiment design;
3. `docs/pentax-mode-aware-liveness.md` — long-exposure/NR/Pixel Shift semantics;
4. `docs/pentax-k1ii-second-pass.md` — K-1 II validation strategy.

## Objective

Use the physically connected Pentax environment to discover repeatable **initiating failure recipes**. Do not begin by making reset/retry more aggressive.

## Critical operating model

The agent is responsible for steering the physical operative. The operative cannot be expected to know whether a test belongs on the PC or Polaris.

For every experiment the agent must choose and state one of:

- **Layer A — camera attached to PC, direct libgphoto2/gphoto2 path**;
- **Layer B — camera attached to PC, Benro/pgphoto-compatible harness path**;
- **Layer C — camera attached to real Polaris, actual embedded path**.

The agent MUST explicitly tell the operative when to move the camera USB between PC and Polaris, and MUST verify the expected camera is enumerated on the new host before running a test. Never infer attachment from a stale model/port cache.

Batch tests by host to minimise cable moves. Do not ask for a move merely because the next scenario number changed.

### Default progression

For a hypothesis that can be tested below Polaris:

```text
Layer A / PC direct
    |
    +-- reproduces -> minimise/fix at A; Polaris reproduction is not required to prove the lower-layer defect
    |
    +-- clean -> Layer B / PC Benro-compatible harness if applicable
                    |
                    +-- reproduces -> integration/command-lifecycle family
                    |
                    +-- clean -> Layer C / real Polaris
```

For an inherently Polaris-specific hypothesis (watchdog, camera_usb_supervisor, embedded USB, Wi-Fi/8080/resource pressure, FwPkt/runtime-loader behaviour), go directly to Layer C after explicitly asking the operative to attach the camera to Polaris.

## First implementation task

Adapt `tools/pentax_stability_trace.py` around both the PC harness and the real Polaris pgphoto/libgphoto2 path. The recorder is intentionally observation-only; do not replace existing deterministic camera control with Python wrappers unless required.

Populate/execute `tests/pentax_stability_scenarios.csv` and `tests/pentax_stability_matrix.json` using the A/B/C layer attribution. Every result must record:

```text
CAMERA=K-3 III|K-1 II
ATTACHMENT=PC|POLARIS
LAYER=A|B|C
PATH=<actual software path>
```

A result without these fields is insufficient for layer attribution.

## Physical operative interaction

Before a host change, stop/close camera-owning processes on the old host and ensure no capture is active. Then issue the exact physical instruction from `docs/pentax-physical-operative-runbook.md`.

The operative should only perform explicitly requested physical actions: cable move, camera power-cycle, USB reconnect, USB Compatibility change, or other stated manipulation. The agent must not bundle several recovery actions together because that destroys causal evidence.

After the operative confirms a cable move, verify enumeration in software before continuing. If verification fails, STOP the experiment and diagnose attachment/USB state.

For destructive fault injection, arm the test first and tell the operative exactly when to act; do not ask them to estimate exposure/processing completion.

## Initial K-3 III execution order

Start with a PC session wherever the hypothesis is supported:

1. E4/E5 consecutive DNG+JPEG candidate lifecycle;
2. E1 95/99/100/101/105 second boundary sweep;
3. E2 concurrency tests supported by the PC harness;
4. E6 120/300 second completion/readout/NR boundary;
5. E13 overlapping shutter;
6. direct-driver soak/control.

Then, without moving the cable, run Layer B equivalents for Layer-A-clean cases where the Benro/pgphoto-compatible harness can reproduce the relevant sequencing.

Only then ask the operative for the **PC -> Polaris physical move** and run Layer C differential/embedded tests, including preview races, real pgphoto/watchdog/session-history, embedded soak and recovery.

Do not run destructive E7-E9 until normal lifecycle traces are understood.

## K-1 II second pass

After K-3 III causal discovery is sufficiently mature, explicitly ask the operative to substitute the K-1 II and repeat the same host progression:

1. K-1 II attached to PC — high-information Layer A subset;
2. same PC attachment — Layer B where applicable;
3. explicit physical move to Polaris — Layer C comparison;
4. expand only experiment families that differ or require generic-Pentax validation.

Do not copy K-3 III timing/candidate assumptions into K-1 II.

## Required discipline

- Keep OpenPolaris out of the first diagnostic path.
- Keep preview OFF for the initial baseline.
- Change one variable at a time.
- A/B/A repetition where practical (distinct from Layer A/B/C naming).
- Repeat failures and report failures/runs.
- Mark the first divergence as `first_abnormal`; do not label a later stale session as root cause without evidence.
- Preserve paired Mlog/Clog for Polaris runs and exact patcher/libgphoto2 SHAs everywhere.
- Never delete/purge an unknown DNG candidate merely to clear state.
- Never classify a multi-minute exposure as dead solely because elapsed time crossed a fixed timeout.
- Do not allow LLM/heuristic runtime decisions to control session ownership or candidate reconciliation.

## Expected deliverables

For each reproducible failure family, add/update a focused GitHub issue containing:

- minimal reproduction;
- exact first abnormal event;
- camera, attachment, layer and actual software path;
- trace excerpt and raw trace artifact/location;
- Mlog/Clog correlation for Polaris tests;
- layer attribution;
- source path/function implicated;
- deterministic proposed fix;
- regression test;
- evidence distinguishing cause from aftermath.

Cross-reference #82 as the field-stability umbrella.

## Stop conditions

If a test risks repeated camera lock/power-cycle, DNG loss, filesystem corruption, uncontrolled process restart loops, or ambiguous physical state, stop that branch and document the evidence obtained. Prefer observability over destructive repetition.
