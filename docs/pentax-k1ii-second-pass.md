# Pentax K-1 II second-pass stability validation

## Intent

K-3 III is the discovery body for the current causal stability campaign. K-1 II is the **second pass** used to determine which findings are generic Pentax/PTP lifecycle defects and which are K-3 III-specific.

Do not blindly rerun every K-3 III test first. Run the highest-information cross-body tests, compare traces, then expand where behaviour differs.

Execution MUST follow `docs/pentax-physical-operative-runbook.md`. The agent, not the human operative, decides when the K-1 II belongs on the PC versus Polaris and explicitly requests each physical move.

## Physical sequence for Pass 2

Minimise cable/body moves by using this order:

1. Agent asks operative to disconnect the K-3 III only when the current campaign is safely stopped.
2. Agent asks operative to connect **K-1 II to the test PC**.
3. Agent verifies K-1 II enumeration on the PC and logs `ATTACHMENT=PC`, `CAMERA=K-1 II`, `LAYER=A`.
4. Run the high-information direct Layer A batch.
5. Keep the cable on the PC and run Layer B Benro/pgphoto-compatible tests where applicable; log `LAYER=B` and actual path.
6. Agent stops all PC camera-owning processes and confirms no capture is active.
7. Agent explicitly asks operative to move **K-1 II from PC to Polaris**.
8. Agent verifies fresh/current K-1 II enumeration on Polaris; a cached camera name or old `usb:BUS,DEVICE` is not proof.
9. Run Layer C embedded comparisons.
10. Only request power-cycle, USB reconnect, USB Compatibility change or Polaris reboot separately and when evidence requires it.

The operative should never have to infer when to move the camera.

## Why K-1 II matters

Existing field evidence already shows K-1 II-specific instability around preview/session handling, including the NoUpdateImage family and body-swap/stale runtime state. Its parameter/control capabilities should not be assumed absent merely because a current runtime path fails to expose them; prior interoperability evidence showed the body supports relevant controls.

The K-1 II pass therefore serves two purposes:

1. validate fixes/invariants discovered on K-3 III;
2. deliberately search for older-body protocol/timing differences hidden by a K-3 III-only design.

## Pass ordering

### Pass 2A — PC/direct cross-body invariants

Run first with K-1 II attached to PC:

- consecutive DNG+JPEG capture and candidate reconciliation (E4/E5);
- 99/100/101 s timeout boundary (E1);
- 120 s normal and NR completion-boundary test (E6);
- direct session/capture soak appropriate to Layer A.

Compare K-1 II traces against equivalent K-3 III traces event-by-event rather than only PASS/FAIL.

### Pass 2B — PC Benro-compatible integration

Without moving the camera from the PC, run applicable harness tests:

- one preview/status command during exposure (E2);
- overlapping/serialized command behaviour;
- candidate/completion sequencing using Benro/pgphoto-compatible semantics.

Record any ways the PC harness differs from real pgphoto; do not conceal those gaps.

### Pass 2C — real Polaris

Only after the PC batch, ask the operative to move K-1 II to Polaris and verify current enumeration. Then run:

- preview/capture race (E3);
- pgphoto restart with body continuously attached and prior-preview history (E12);
- embedded short-capture soak (E11);
- real watchdog/supervisor/recovery cases;
- any A/B-clean scenario requiring Layer C differential confirmation.

### Pass 2D — expand divergences

If K-1 II differs, expand only the relevant family to the full K-3 III sweep. Examples:

- if 100 s boundary differs, run 95/99/100/101/105 and longer astro exposures;
- if preview differs, sweep cadence and capture/preview offsets;
- if candidate semantics differ, enumerate descriptors and repeat all safe transfer/reconciliation permutations;
- if session-history differs, expand fresh/warm/body-reconnect/process-restart combinations.

### Pass 2E — K-1 II-specific destructive stress

After non-destructive characterisation, add cancellation/process/USB tests where needed. Do not assume K-3 III recovery behaviour applies. The agent must arm the experiment and give the operative an exact physical trigger rather than asking them to estimate camera state.

## Mode handling

Use the same fundamental rule as K-3 III:

```
physical exposures != processing phases != output files != tether candidates
```

Do not transplant K-3 III Pixel Shift/NR timings or candidate counts into K-1 II logic. Characterise K-1 II hardware independently for modes it supports.

Requested shutter + mode provide an expected operation envelope only. Camera/PTP state and transport/process health remain authoritative for liveness.

## Preview-specific attention

K-1 II has strong prior evidence around embedded preview failures. For the K-1 II pass record, at minimum:

- whether session was freshly opened or reported already open;
- live-view setup/entry result;
- each get-frame result and byte count;
- restore-after-frame result;
- retry count and total elapsed time;
- whether preview requests continue while another camera lifecycle owns the session;
- Wi-Fi/8080 health separately from camera/PTP health.

A bounded inner retry is not sufficient if an outer loop immediately starts another retry cycle indefinitely.

## Session/body identity

K-1 II has also contributed evidence to stale selected abilities/port state. Validate that removal/reconnect or switching bodies never reuses a vanished explicit `usb:BUS,DEVICE` selection.

Record current USB identity and selected camera abilities at every init/reset. A new physical body/session must be detected from current inventory, not inherited from cached application state.

## Cross-body result classification

For each failure/fix classify it as:

- `GENERIC_PENTAX` — same first divergence and mechanism on both bodies;
- `K3III_SPECIFIC` — only K-3 III reproduces with equivalent conditions;
- `K1II_SPECIFIC` — only K-1 II reproduces;
- `SHARED_SYMPTOM_DIFFERENT_CAUSE` — same eventual symptom but different first divergence;
- `UNKNOWN` — insufficient evidence.

This classification belongs in the focused issue/regression test. Do not call something generic Pentax merely because both cameras eventually need a reset.

## Release implication

A K-3 III fix is not a Pentax-wide fix until the relevant invariant passes on K-1 II. Conversely, a K-1 II preview workaround must not degrade the K-3 III path.

Final release qualification should still exercise each body independently through the full regression gate after causal fixes land.
